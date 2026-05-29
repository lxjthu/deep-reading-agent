from __future__ import annotations

import argparse
import json
import time

import httpx


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Probe large-batch agent analysis SSE behavior.")
    parser.add_argument("--base-url", required=True, help="Base URL, e.g. http://127.0.0.1:8000")
    parser.add_argument("--email", required=True)
    parser.add_argument("--password", required=True)
    parser.add_argument("--api-key", required=True)
    parser.add_argument(
        "--message",
        default="对没有启动精读的文献做个分类总结，并根据文献发表的期刊质量列出可以优先精读的文献，做个表格。",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    started_at = time.time()
    first_progress_at: float | None = None

    with httpx.Client(timeout=600.0) as client:
        login = client.post(
            f"{args.base_url.rstrip('/')}/api/auth/login",
            json={"email": args.email, "password": args.password},
        )
        login.raise_for_status()
        token = login.json()["access_token"]
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }

        with client.stream(
            "POST",
            f"{args.base_url.rstrip('/')}/api/agent/chat",
            headers=headers,
            json={
                "message": args.message,
                "api_key": args.api_key,
                "history": [],
            },
        ) as response:
            response.raise_for_status()
            buffer = ""
            for chunk in response.iter_text():
                buffer += chunk
                blocks = buffer.split("\n\n")
                buffer = blocks.pop() or ""
                for block in blocks:
                    event_name = ""
                    data = None
                    for line in block.splitlines():
                        if line.startswith("event: "):
                            event_name = line[7:].strip()
                        elif line.startswith("data: "):
                            data = json.loads(line[6:])
                    if not event_name:
                        continue
                    if event_name == "analysis_progress":
                        if first_progress_at is None:
                            first_progress_at = time.time()
                        print(
                            f"[analysis_progress] {data.get('processed_count', 0)}/{data.get('total_count', 0)} "
                            f"batch={data.get('batch_index')} top_clusters={data.get('top_clusters')}"
                        )
                    elif event_name == "answer":
                        print(f"[answer] {str(data.get('content') or '')[:300]}")
                    elif event_name == "runtime_notice":
                        print(f"[runtime_notice] {data}")
                    elif event_name == "error":
                        print(f"[error] {data}")
                    elif event_name == "done":
                        break

    elapsed = time.time() - started_at
    print(f"total_elapsed={elapsed:.2f}s")
    if first_progress_at is not None:
        print(f"first_progress_elapsed={first_progress_at - started_at:.2f}s")
    else:
        print("first_progress_elapsed=not_emitted")


if __name__ == "__main__":
    main()
