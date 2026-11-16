#!/usr/bin/env python3
"""校验 plugins/*.json 与 releases/*.json 的静态元数据（PR 与 CI 使用）。"""

from __future__ import annotations

import json
import re
import sys
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parent.parent
PLUGINS_DIR = ROOT / "plugins"
RELEASES_DIR = ROOT / "releases"
PLUGIN_ID_RE = re.compile(r"^[a-z][a-z0-9_]*$")
REPO_RE = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
VERSION_RE = re.compile(r"^\d+\.\d+\.\d+$")
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
DIGEST_RE = re.compile(r"^sha256:([0-9a-f]{64})$")
VALID_CATEGORIES = {
    "storage",
    "metadata",
    "discovery",
    "automation",
    "subtitle",
    "other",
}
SOURCE_EXTERNAL = "external"
SOURCE_MARKET = "market"
VALID_SOURCES = {SOURCE_EXTERNAL, SOURCE_MARKET}
REQUIRED_FIELDS = (
    "plugin_id",
    "display_name",
    "description",
    "author",
    "repo",
    "homepage",
    "categories",
    "official",
)
LATEST_FIELDS = (
    "version",
    "host_api_version",
    "download_url",
    "sha256",
    "published_at",
)
# 多语言字典字段：缺失是合法的（插件不做多语言），存在时必须覆盖这两种语言。
I18N_FIELDS = ("display_name_i18n", "description_i18n")
REQUIRED_LOCALES = ("zh-CN", "en")


def _valid_http_url(value: object) -> bool:
    if not isinstance(value, str):
        return False
    parsed = urlparse(value)
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)


def _valid_timestamp(value: object) -> bool:
    if value is None:
        return True
    if not isinstance(value, str):
        return False
    try:
        datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return False
    return True


def validate_plugin(path: Path, data: dict, seen: set[str]) -> list[str]:
    errors: list[str] = []
    name = path.name
    for field in REQUIRED_FIELDS:
        if field not in data:
            errors.append(f"{name}: 缺少字段 {field}")

    plugin_id = data.get("plugin_id", "")
    if not isinstance(plugin_id, str) or not PLUGIN_ID_RE.match(
        plugin_id
    ) or len(plugin_id) > 64:
        errors.append(f"{name}: plugin_id 非法: {plugin_id!r}")
    elif path.stem != plugin_id:
        errors.append(f"{name}: 文件名应与 plugin_id 一致")
    elif plugin_id in seen:
        errors.append(f"{name}: plugin_id 重复")
    else:
        seen.add(plugin_id)

    source = data.get("source", SOURCE_EXTERNAL)
    if source not in VALID_SOURCES:
        errors.append(f"{name}: source 必须是 {sorted(VALID_SOURCES)} 之一: {source!r}")

    repo = data.get("repo", "")
    if not isinstance(repo, str) or not REPO_RE.match(repo):
        errors.append(f"{name}: repo 必须是 owner/name 格式: {repo!r}")

    categories = data.get("categories")
    if not isinstance(categories, list) or not categories:
        errors.append(f"{name}: categories 必须是非空数组")
    else:
        unknown = set(categories) - VALID_CATEGORIES
        if unknown:
            errors.append(f"{name}: 未知分类 {sorted(unknown)}")

    if not isinstance(data.get("official"), bool):
        errors.append(f"{name}: official 必须是布尔值")

    description = data.get("description")
    if not isinstance(description, str) or not 1 <= len(description) <= 200:
        errors.append(f"{name}: description 长度必须在 1-200 之间")

    for field in I18N_FIELDS:
        errors.extend(_validate_i18n_map(name, field, data.get(field)))

    errors.extend(_validate_latest(name, data, source))
    return errors


def _validate_i18n_map(name: str, field: str, value: object) -> list[str]:
    """校验多语言字典：必须是 {语言标签: 非空字符串}。

    字典整体缺失是合法的（插件不做多语言）；存在时两个语言都要有，避免英文
    界面因为漏了 zh-CN 或 en 而露出另一种语言的文案。
    """
    if value is None:
        return []
    if not isinstance(value, dict):
        return [f"{name}: {field} 必须是对象"]
    errors: list[str] = []
    for locale, text in value.items():
        if not isinstance(locale, str) or not locale.strip():
            errors.append(f"{name}: {field} 的语言标签必须是非空字符串")
            continue
        if not isinstance(text, str) or not text.strip():
            errors.append(f"{name}: {field}.{locale} 必须是非空字符串")
    missing = [locale for locale in REQUIRED_LOCALES if locale not in value]
    if missing:
        errors.append(f"{name}: {field} 缺少语言 {missing}")
    return errors


def _validate_latest(name: str, data: dict, source: str) -> list[str]:
    if "latest" not in data:
        if source == SOURCE_MARKET:
            return [f"{name}: source=market 必须包含 latest"]
        return []
    latest = data["latest"]
    if not isinstance(latest, dict):
        return [f"{name}: latest 必须是对象"]
    errors: list[str] = []
    missing = [field for field in LATEST_FIELDS if field not in latest]
    if missing:
        errors.append(f"{name}: latest 缺少字段 {missing}")
        return errors

    version = latest["version"]
    if not isinstance(version, str) or not VERSION_RE.fullmatch(version):
        errors.append(f"{name}: latest.version 必须是三段版本号: {version!r}")

    host_api_version = latest["host_api_version"]
    if (
        not isinstance(host_api_version, int)
        or isinstance(host_api_version, bool)
        or host_api_version < 1
    ):
        errors.append(
            f"{name}: latest.host_api_version 必须是正整数: {host_api_version!r}"
        )

    if not _valid_http_url(latest["download_url"]):
        errors.append(f"{name}: latest.download_url 必须是 http(s) URL")

    sha256 = latest["sha256"]
    if not isinstance(sha256, str) or not SHA256_RE.fullmatch(sha256):
        errors.append(f"{name}: latest.sha256 必须是 64 位小写十六进制")

    if not _valid_timestamp(latest["published_at"]):
        errors.append(f"{name}: latest.published_at 必须是 ISO 时间或 null")

    return errors


def validate_release(
    path: Path,
    data: dict,
    plugins_by_id: dict[str, dict],
) -> list[str]:
    errors: list[str] = []
    name = path.name
    plugin_id = path.stem
    entry = plugins_by_id.get(plugin_id)
    if entry is None:
        errors.append(f"{name}: 没有对应的 plugins/{plugin_id}.json")
    elif entry.get("source", SOURCE_EXTERNAL) != SOURCE_MARKET:
        errors.append(f"{name}: 只有 source=market 的插件需要 releases 文件")

    required = ("tag_name", "name", "body", "published_at", "assets")
    missing = [field for field in required if field not in data]
    if missing:
        errors.append(f"{name}: 缺少字段 {missing}")
        return errors

    version = None
    tag = data["tag_name"]
    if not isinstance(tag, str) or not tag.startswith("v"):
        errors.append(f"{name}: tag_name 必须是 v<version>: {tag!r}")
    elif not VERSION_RE.fullmatch(tag[1:]):
        errors.append(f"{name}: tag_name 版本号必须是三段格式: {tag!r}")
    else:
        version = tag[1:]

    if not isinstance(data["name"], str) or not data["name"].strip():
        errors.append(f"{name}: name 必须是非空字符串")
    if not isinstance(data["body"], str):
        errors.append(f"{name}: body 必须是字符串")
    if not _valid_timestamp(data["published_at"]):
        errors.append(f"{name}: published_at 必须是 ISO 时间或 null")

    assets = data["assets"]
    if not isinstance(assets, list) or len(assets) != 1:
        errors.append(f"{name}: assets 必须只包含一个 zip 资产")
        assets = []
    asset = assets[0] if assets else None
    digest_hex = None
    if asset is not None:
        if not isinstance(asset, dict):
            errors.append(f"{name}: assets[0] 必须是对象")
            asset = None
        else:
            if not isinstance(asset.get("name"), str) or not asset["name"].strip():
                errors.append(f"{name}: assets[0].name 必须是非空字符串")
            if not _valid_http_url(asset.get("browser_download_url")):
                errors.append(f"{name}: assets[0].browser_download_url 必须是 http(s) URL")
            digest = asset.get("digest")
            match = DIGEST_RE.fullmatch(digest) if isinstance(digest, str) else None
            if match is None:
                errors.append(
                    f"{name}: assets[0].digest 必须是 sha256:<64 位小写十六进制>"
                )
            else:
                digest_hex = match.group(1)

    if entry is not None and asset is not None:
        latest = entry.get("latest")
        if not isinstance(latest, dict):
            errors.append(f"{name}: 对应插件缺少 latest，无法交叉校验")
        else:
            if version is not None and latest.get("version") != version:
                errors.append(
                    f"{name}: latest.version({latest.get('version')!r}) 与 "
                    f"tag_name({version!r}) 不一致"
                )
            if latest.get("download_url") != asset.get("browser_download_url"):
                errors.append(f"{name}: latest.download_url 与资产 URL 不一致")
            if digest_hex is not None and latest.get("sha256") != digest_hex:
                errors.append(f"{name}: latest.sha256 与资产 digest 不一致")
            if latest.get("published_at") != data["published_at"]:
                errors.append(f"{name}: latest.published_at 与 published_at 不一致")

    return errors


def main() -> int:
    errors: list[str] = []
    seen: set[str] = set()
    plugins_by_id: dict[str, dict] = {}
    paths = sorted(PLUGINS_DIR.glob("*.json"))
    if not paths:
        print("plugins/ 下没有元数据文件", file=sys.stderr)
        return 1
    for path in paths:
        try:
            with path.open(encoding="utf-8") as handle:
                data = json.load(handle)
        except json.JSONDecodeError as error:
            errors.append(f"{path.name}: JSON 解析失败: {error}")
            continue
        if not isinstance(data, dict):
            errors.append(f"{path.name}: 顶层必须是对象")
            continue
        plugin_id = data.get("plugin_id")
        if isinstance(plugin_id, str):
            plugins_by_id[plugin_id] = data
        errors.extend(validate_plugin(path, data, seen))

    release_paths = sorted(RELEASES_DIR.glob("*.json")) if RELEASES_DIR.is_dir() else []
    for path in release_paths:
        try:
            with path.open(encoding="utf-8") as handle:
                data = json.load(handle)
        except json.JSONDecodeError as error:
            errors.append(f"{path.name}: JSON 解析失败: {error}")
            continue
        if not isinstance(data, dict):
            errors.append(f"{path.name}: 顶层必须是对象")
            continue
        errors.extend(validate_release(path, data, plugins_by_id))

    if errors:
        for error in errors:
            print(f"校验失败: {error}", file=sys.stderr)
        return 1
    print(
        f"校验通过，共 {len(seen)} 个插件，"
        f"{len(release_paths)} 份 Release 元数据"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
