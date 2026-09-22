#!/usr/bin/env python3
"""Dump per-round parent visibility after attack start, matching the hand-written format."""
from __future__ import annotations

import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROUND_RE = re.compile(r"\bRound\s+(\d+):\s+(.*)")
VERTEX_RE = re.compile(r"\(Vertex(\d+)\)")
PARENT_RE = re.compile(r"\[(w?)(\d+|\?),\s*(\d+|\?)\]")
COMMIT_RE = re.compile(
    r"DAG_COMMIT_CHECK\s+path=(?P<path>\S+)\s+"
    r"leader_round=(?P<leader_round>\d+)\s+"
    r"leader_node=(?P<leader_node>\d+)\s+"
    r"support_round=(?P<support_round>\d+)\s+"
    r"support_basis=(?P<support_basis>\S+)\s+"
    r"(?:trigger_round=(?P<trigger_round>\d+)\s+)?"
    r"stake=(?P<stake>\d+)\s+"
    r"threshold=(?P<threshold>\d+)\s+"
    r"result=(?P<result>\S+)\s+"
    r"support_set=\[(?P<support_set>[^\]]*)\]"
)
TS_RE = re.compile(r"^\[(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d+)Z")
N = 10


def parse_ts(line: str):
    m = TS_RE.match(line)
    if not m:
        return None
    return datetime.fromisoformat(m.group(1)).replace(tzinfo=timezone.utc)


def leader_of(round_no: int) -> int:
    return round_no % N


def parse_round_payload(payload: str):
    vertices = {}
    unknown = 0
    for chunk in payload.split(" --- "):
        vm = VERTEX_RE.search(chunk)
        if not vm:
            continue
        vid = int(vm.group(1))
        prefix = chunk.split(" (solid_wave_vertices:", 1)[0]
        parent_blob = prefix[vm.end() :].split(" weak=", 1)[0]
        strong = []
        for pm in PARENT_RE.finditer(parent_blob):
            wflag, pr, pn = pm.groups()
            if pr == "?" or pn == "?":
                unknown += 1
                continue
            if wflag == "w":
                continue
            strong.append((int(pr), int(pn)))
        vertices[vid] = strong
    return vertices, unknown


def scan_primary(path: Path, attack_ts):
    """First complete 10/10 snapshot per round after attack_ts.

    Also returns start_round: the first `Round N` dumped after attack.
    visualize_dag prints current_round first (descending), so that N is
    the live round when the attack begins.
    """
    first = {}
    commits = []
    start_round = None
    with path.open("rb") as f:
        for raw in f:
            if (
                b"Round " not in raw
                and b"DAG_COMMIT_CHECK" not in raw
            ):
                continue
            line = raw.decode("utf-8", errors="replace")
            ts = parse_ts(line)
            if attack_ts and ts and ts < attack_ts:
                continue
            m = COMMIT_RE.search(line)
            if m:
                rec = m.groupdict()
                rec["ts"] = ts
                rec["stake"] = int(rec["stake"])
                rec["threshold"] = int(rec["threshold"])
                rec["leader_round"] = int(rec["leader_round"])
                rec["support_round"] = int(rec["support_round"])
                rec["support_set"] = [
                    int(x) for x in rec["support_set"].split(",") if x.strip()
                ]
                commits.append(rec)
                continue
            if b"Round " not in raw:
                continue
            rm = ROUND_RE.search(line)
            if not rm:
                continue
            r = int(rm.group(1))
            if start_round is None:
                start_round = r
            if r < start_round:
                continue
            if r in first:
                continue
            verts, unknown = parse_round_payload(rm.group(2))
            if unknown:
                continue
            if len(verts) != N or set(verts) != set(range(N)):
                continue
            first[r] = {"ts": ts, "verts": verts}
    return start_round, first, commits


def fmt_ts(ts) -> str:
    if ts is None:
        return "?"
    return ts.strftime("%Y-%m-%dT%H:%M:%S.") + f"{int(ts.microsecond/1000):03d}Z"


def fmt_parents(parents, prev_round, prev_leader):
    prev = [(pr, pn) for pr, pn in parents if pr == prev_round]
    prev.sort(key=lambda x: x[1])
    parts = []
    for pr, pn in prev:
        star = "*" if pn == prev_leader else ""
        parts.append(f"{pr}:{pn}{star}")
    return "  ".join(parts), {pn for pr, pn in prev}


def dump_run(run_dir: Path, out_path: Path, kappa: int, reference: int, coverage: int):
    logs = sorted((run_dir / "logs").glob("primary-*.log"))
    if not logs:
        raise SystemExit(f"no primary logs in {run_dir}")

    # Attack at primary start + 60s (matches the hand-written dump header).
    p0 = run_dir / "logs" / "primary-0.log"
    first_ts = None
    start_attack_log_ts = None
    with p0.open("rb") as f:
        for raw in f:
            line = raw.decode("utf-8", errors="replace")
            ts = parse_ts(line)
            if first_ts is None and ts is not None:
                first_ts = ts
            if b"start attack" in raw:
                start_attack_log_ts = ts
                break
    if first_ts is None:
        raise SystemExit(f"no timestamp in {p0}")
    attack_ts = first_ts + timedelta(seconds=60)
    print(
        f"  first_ts={fmt_ts(first_ts)} attack={fmt_ts(attack_ts)} "
        f"start_attack_log={fmt_ts(start_attack_log_ts)}",
        flush=True,
    )

    per_primary = {}
    commits_p0 = []
    start_round = None
    for lp in logs:
        idx = int(re.search(r"primary-(\d+)\.log", lp.name).group(1))
        print(f"  scan {lp.name}", flush=True)
        sr, first, commits = scan_primary(lp, attack_ts)
        per_primary[idx] = first
        if idx == 0:
            commits_p0 = commits
            start_round = sr
    if start_round is None:
        raise SystemExit(f"no Round dump after attack in {p0}")

    commits_by_leader = {}
    for c in commits_p0:
        commits_by_leader.setdefault(c["leader_round"], []).append(c)

    # Union of live rounds (current at attack start and later).
    all_rounds = sorted(
        {
            r
            for snaps in per_primary.values()
            for r in snaps
            if r >= start_round
        }
    )
    print(f"  start_round={start_round} complete_rounds={len(all_rounds)}", flush=True)
    chosen = []
    for r in all_rounds:
        pick = None
        src = None
        for idx in range(N):
            snap = per_primary.get(idx, {}).get(r)
            if snap:
                pick = snap
                src = idx
                break
        if pick:
            chosen.append((r, src, pick))

    lines = []
    lines.append("攻击开始后各顶点看到了谁（含 leader）")
    lines.append(
        f"run: k={kappa}  ref={reference}  coverage={coverage}  n=10  sigma=1"
    )
    lines.append(f"目录: {run_dir.name}")
    lines.append(f"攻击起点: {fmt_ts(attack_ts)} （primary 启动后第 60 秒）")
    lines.append("这份文件只保留攻击起点之后、父引用已完整解析的轮次。")
    lines.append("")
    lines.append("怎么读")
    lines.append("  leader(round) = round % 10。")
    lines.append("  每个顶点下面一行是它直接引用的父顶点，写成 父轮次:作者。")
    lines.append("  作者后面的 * 表示这个作者就是该父轮次的 leader。")
    lines.append("  sees_prev_leader=YES 表示父引用里包含上一轮的 leader。")
    lines.append(
        "  提交检查来自 primary-0。support_set 是支持轮里、solid 集合覆盖到该 leader 的顶点编号。"
    )
    lines.append("")

    saw_counts = []
    nobody = 0
    for r, src, snap in chosen:
        prev = r - 1
        cur_leader = leader_of(r)
        prev_leader = leader_of(prev)
        dt = ""
        if snap["ts"] and attack_ts:
            dt = f"{(snap['ts'] - attack_ts).total_seconds():.2f}"
        else:
            dt = "?"
        lines.append("=" * 78)
        lines.append(
            f"Round {r}    attack+{dt}s    snapshot=primary-{src}    完整顶点=10/10"
        )
        lines.append(f"本轮 leader = 顶点 {cur_leader}")
        lines.append(f"上一轮 Round {prev} 的 leader = 顶点 {prev_leader}")
        lines.append("-" * 78)

        saw = []
        parent_sets = []
        saw_sets = []
        for vid in range(N):
            parents = snap["verts"][vid]
            blob, prev_authors = fmt_parents(parents, prev, prev_leader)
            yes = prev_leader in prev_authors
            lines.append(
                f"vertex {vid}    sees_prev_leader={'YES' if yes else 'no'}"
            )
            lines.append(f"    {blob}")
            parent_sets.append(prev_authors)
            if yes:
                saw.append(vid)
                saw_sets.append(prev_authors)
        n_saw = len(saw)
        saw_counts.append(n_saw)
        if n_saw == 0:
            nobody += 1
            saw_txt = "无"
            inter_src = parent_sets
        else:
            saw_txt = str(saw)
            inter_src = saw_sets
        inter = set.intersection(*inter_src) if inter_src else set()
        inter_sorted = sorted(inter)
        has_leader = prev_leader in inter
        lines.append(
            f"看到上一轮 leader {prev_leader} 的顶点: {saw_txt}    共 {n_saw}/10"
        )
        lines.append(
            f"这些顶点对 Round {prev} 的共同父作者: {inter_sorted}    "
            f"其中包含 leader {prev_leader}: {'YES' if has_leader else 'no'}"
        )
        checks = commits_by_leader.get(r, [])
        if checks:
            seen = set()
            uniq = []
            for c in checks:
                key = (
                    c["support_round"],
                    c["stake"],
                    c["result"],
                    tuple(c["support_set"]),
                )
                if key in seen:
                    continue
                seen.add(key)
                uniq.append(c)
            lines.append(f"primary-0 对本轮 leader {cur_leader} 的提交检查:")
            for c in uniq:
                ss = ",".join(str(x) for x in c["support_set"])
                lines.append(
                    f"    support_round={c['support_round']}  "
                    f"stake={c['stake']}/{c['threshold']}  "
                    f"result={c['result']}  support_set=[{ss}]"
                )
        lines.append("")

    if chosen:
        lo, hi = chosen[0][0], chosen[-1][0]
        saw_sorted = sorted(saw_counts)
        med = saw_sorted[len(saw_sorted) // 2]
        lines.append("=" * 78)
        lines.append("汇总")
        lines.append(f"写出的轮次: {len(chosen)}    Round {lo} .. {hi}")
        lines.append(
            f"每轮有多少个完整顶点引用了上一轮 leader: 最少 {min(saw_counts)}  中位 {med}  最多 {max(saw_counts)}"
        )
        lines.append(f"上一轮 leader 完全没人引用的轮次: {nobody}/{len(chosen)}")
        lines.append("")

    out_path.write_text("\n".join(lines) + "\n")
    also = run_dir / "attack_window_who_sees_whom.txt"
    also.write_text(out_path.read_text())
    print(f"WROTE {out_path} and {also} rounds={len(chosen)}")


def main():
    base = Path(
        "/users/michael9/manta_yu/benchmark/manta_result/debug_new/geo/k2c7"
    )
    jobs = [
        (
            base
            / "20260921_154407_535488_cloudlab-n10-r100000-run1-s1-k2-ref7-tag-debug_new",
            base / "attack_window_who_sees_whom_k2c7.txt",
            2,
            7,
            7,
        ),
        (
            base
            / "20260921_154859_760488_cloudlab-n10-r100000-run1-s1-k3-ref7-tag-debug_new",
            base / "attack_window_who_sees_whom_k3c7.txt",
            3,
            7,
            7,
        ),
    ]
    only = sys.argv[1:]
    for run_dir, out, k, ref, cov in jobs:
        if only and f"k{k}" not in only and run_dir.name not in only:
            continue
        print("====", run_dir.name, "====", flush=True)
        dump_run(run_dir, out, k, ref, cov)


if __name__ == "__main__":
    main()
