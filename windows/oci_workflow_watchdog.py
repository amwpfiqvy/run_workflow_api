#!/usr/bin/env python3
"""通过 GitHub API 监控并按需手动触发 OCI ARM 工作流。"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import time
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any


OWNER = "amwpfiqvy"
REPO = "oci-arm-host-capacity"
WORKFLOW_FILE = "oci-arm-capacity.yml"
DEFAULT_REF = "main"
THRESHOLD_SECONDS = 420
API_VERSION = "2022-11-28"
USER_AGENT = "oci-arm-watchdog"
DEFAULT_PROXY = "http://127.0.0.1:7897"
POLL_SECONDS = 20
LOG_DIR = Path(__file__).resolve().parent / "logs"
TOKEN_FILE = Path(__file__).resolve().parent / "token"
LOG_KEEP_DAYS = 7


class WatchdogError(RuntimeError):
    """可直接反馈给定时任务用户的错误。"""


def write_log(message: str) -> None:
    """记录固定日期日志；不把日志内容混入 stdout。"""
    try:
        LOG_DIR.mkdir(parents=True, exist_ok=True)
        today = datetime.now().date()
        for path in LOG_DIR.glob("*.log"):
            try:
                if today - datetime.fromtimestamp(
                    path.stat().st_mtime
                ).date() > timedelta(days=LOG_KEEP_DAYS):
                    path.unlink()
            except OSError:
                continue
        stamp = datetime.now().astimezone().isoformat(timespec="seconds")
        with (LOG_DIR / f"{today.isoformat()}.log").open(
            "a", encoding="utf-8"
        ) as stream:
            stream.write(f"{stamp} {message}\n")
    except OSError:
        pass


def load_token() -> str:
    for key in ("GITHUB_TOKEN", "GH_TOKEN"):
        value = os.environ.get(key, "").strip()
        if value:
            return value
    if TOKEN_FILE.is_file():
        text = TOKEN_FILE.read_text(encoding="utf-8")
        for line in text.splitlines():
            value = line.strip()
            if value and not value.startswith("#"):
                return value
    gh = shutil.which("gh")
    if gh:
        try:
            completed = subprocess.run(
                [gh, "auth", "token"],
                check=False,
                capture_output=True,
                text=True,
                timeout=10,
            )
        except (OSError, subprocess.TimeoutExpired):
            completed = None
        if completed and completed.returncode == 0:
            value = (completed.stdout or "").strip()
            if value:
                return value
    raise WatchdogError(
        "未找到 GitHub token：请设置环境变量 GITHUB_TOKEN/GH_TOKEN，"
        "或在本目录放入 token 文件，或先 gh auth login"
    )


def build_opener(proxy: str | None) -> urllib.request.OpenerDirector:
    if proxy:
        handler = urllib.request.ProxyHandler(
            {"http": proxy, "https": proxy}
        )
        return urllib.request.build_opener(handler)
    return urllib.request.build_opener(urllib.request.ProxyHandler({}))


class GitHubApi:
    def __init__(self, token: str, opener: urllib.request.OpenerDirector) -> None:
        self.token = token
        self.opener = opener

    def request(
        self,
        method: str,
        path: str,
        body: dict[str, Any] | None = None,
        timeout: float = 30,
    ) -> tuple[int, Any]:
        url = f"https://api.github.com{path}"
        data = None if body is None else json.dumps(body).encode("utf-8")
        request = urllib.request.Request(
            url,
            data=data,
            method=method,
            headers={
                "Authorization": f"Bearer {self.token}",
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": API_VERSION,
                "User-Agent": USER_AGENT,
            },
        )
        if data is not None:
            request.add_header("Content-Type", "application/json")
        try:
            with self.opener.open(request, timeout=timeout) as response:
                raw = response.read()
                status = response.status
        except urllib.error.HTTPError as exc:
            raw = exc.read()
            message = decode_error(raw, exc.reason)
            raise WatchdogError(
                f"GitHub API {method} {path} 失败 HTTP {exc.code}：{message}"
            ) from exc
        except urllib.error.URLError as exc:
            raise WatchdogError(f"无法访问 GitHub API（{exc.reason}）") from exc
        if not raw:
            return status, None
        try:
            return status, json.loads(raw.decode("utf-8"))
        except ValueError as exc:
            raise WatchdogError("GitHub API 返回了无法解析的 JSON") from exc

    def latest_run(self) -> dict[str, Any] | None:
        status, payload = self.request(
            "GET",
            f"/repos/{OWNER}/{REPO}/actions/workflows/{WORKFLOW_FILE}/runs"
            "?per_page=1",
        )
        if status != 200 or not isinstance(payload, dict):
            raise WatchdogError("读取工作流运行列表失败")
        runs = payload.get("workflow_runs") or []
        return runs[0] if runs else None

    def dispatch(self, ref: str) -> None:
        status, _payload = self.request(
            "POST",
            f"/repos/{OWNER}/{REPO}/actions/workflows/{WORKFLOW_FILE}/dispatches",
            {"ref": ref},
        )
        if status != 204:
            raise WatchdogError(f"触发工作流失败 HTTP {status}")


def decode_error(raw: bytes, fallback: str) -> str:
    text = raw.decode("utf-8", errors="replace").strip()
    if not text:
        return fallback
    try:
        payload = json.loads(text)
    except ValueError:
        return text[:300]
    message = str(payload.get("message") or fallback)
    errors = payload.get("errors")
    if errors:
        message = f"{message} ({errors})"
    return message[:300]


def parse_github_time(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(
        timezone.utc
    )


def run(args: argparse.Namespace) -> str:
    token = load_token()
    api = GitHubApi(token, build_opener(args.proxy))
    latest = api.latest_run()
    if latest is None:
        raise WatchdogError("找不到可靠的最后一次执行时间，需要人工处理")

    created = parse_github_time(str(latest.get("created_at") or ""))
    age = (datetime.now(timezone.utc) - created).total_seconds()
    if age < args.threshold:
        return "检查完成：最近执行距现在不足7分钟，未执行"

    before_id = latest.get("id")
    api.dispatch(args.ref)

    confirmed: dict[str, Any] | None = None
    deadline = time.monotonic() + POLL_SECONDS
    while time.monotonic() < deadline:
        time.sleep(1)
        current = api.latest_run()
        if current and current.get("id") != before_id:
            confirmed = current
            break
    if confirmed:
        return "已手动执行：运行列表出现新记录"
    return "未确认执行成功：dispatch 后未看到新的运行记录，需要人工检查"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--threshold",
        type=int,
        default=THRESHOLD_SECONDS,
        help="距最近一次运行的最小秒数，默认420",
    )
    parser.add_argument(
        "--ref",
        default=DEFAULT_REF,
        help="workflow_dispatch 使用的 git ref，默认 main",
    )
    parser.add_argument(
        "--proxy",
        default=os.environ.get("HTTPS_PROXY")
        or os.environ.get("https_proxy")
        or os.environ.get("HTTP_PROXY")
        or os.environ.get("http_proxy")
        or DEFAULT_PROXY,
        help="HTTPS 代理，默认 127.0.0.1:7897；传空字符串表示直连",
    )
    args = parser.parse_args()
    if args.proxy == "":
        args.proxy = None
    return args


def main() -> None:
    args = parse_args()
    try:
        result = run(args)
    except WatchdogError as exc:
        result = f"{exc}。"
    except Exception as exc:
        result = f"脚本异常（{exc}），需要人工处理。"
    write_log(result)
    print(result, flush=True)


if __name__ == "__main__":
    main()
