#!/usr/bin/env python3
"""
csv_to_planning.py - convert a planning CSV into the planning JSON format.

Usage:
    python csv_to_planning.py planning.csv
    python csv_to_planning.py planning.csv -o out.json --resources resources.csv

Activities CSV (header names are case-insensitive; delimiter , ; tab or | is auto-detected)
    WBS_ID        required  e.g. 1 / 1.1 / 1.1.1  -> hierarchy and indent are derived from it
    Name          required
    ID            optional  external id; the name becomes "<ID> | <Name>"
    Start         optional* YYYY-MM-DD or DD/MM/YYYY (also DD-MM-YYYY, DD.MM.YYYY)
    Duration      optional* whole days (end = start + duration)
    End           optional* alternative to Duration (duration = end - start)
    Predecessors  optional  WBS_IDs, separated by ; , or |
    Resources     optional  resource names, separated by ; , or |
  * Leaf activities need Start + (Duration or End). A parent activity (one that has
    children) with Start/Duration/End left blank is rolled up from its children.

Resources CSV (optional, --resources)
    Name          required
    Type          optional  default "Human Resource"
    Parent        optional  name of a group row that appears earlier in the file
  Without this file, resources are created from the Resources column (flat list).

Position-based output per activity:
 [0]UUID [1]ActivityNo [2]WBS_ID [3]Name [4]Predecessor [5]StartDate [6]EndDate(empty)
 [7]Duration [8]Successors [9..12] empty (recalculated by the tool)
"""
import argparse, csv, json, re, sys, uuid
from datetime import datetime

ACT_COLS = {
    "wbs_id": {"wbs_id", "wbs", "wbs id", "wbsid"},
    "name": {"name", "activity", "activity name", "task"},
    "id": {"id", "ref", "external id", "external_id"},
    "start": {"start", "start date", "startdate", "start_date"},
    "duration": {"duration", "duration (days)", "days"},
    "end": {"end", "end date", "enddate", "end_date"},
    "predecessors": {"predecessor", "predecessors", "pred"},
    "resources": {"resource", "resources"},
}
RES_COLS = {"name": {"name", "resource"}, "type": {"type", "resource type"}, "parent": {"parent", "group", "team"}}
DATE_FORMATS = ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y", "%Y/%m/%d", "%d.%m.%Y")
NS = uuid.UUID("6f1c2a52-0d57-4c0e-9b52-4b1f3b1a7a10")


def read_csv(path, cols):
    with open(path, newline="", encoding="utf-8-sig") as fh:
        header = fh.readline(); fh.seek(0)
        delim = max(",;\t|", key=header.count)  # detect from the header line only
        reader = csv.DictReader(fh, delimiter=delim)
        mapping = {}
        for h in reader.fieldnames or []:
            for canon, names in cols.items():
                if h.strip().lower() in names:
                    mapping[h] = canon
        rows = []
        for n, raw in enumerate(reader, start=2):
            row = {mapping[k]: (v or "").strip() for k, v in raw.items() if k in mapping}
            if any(row.values()):
                row["_line"] = n
                rows.append(row)
    return rows


def parse_date(text, line):
    for fmt in DATE_FORMATS:
        for suffix in ("", " %H:%M"):
            try:
                return datetime.strptime(text, fmt + suffix).date()
            except ValueError:
                pass
    raise ValueError(f"line {line}: cannot read date '{text}' (use YYYY-MM-DD or DD/MM/YYYY)")


def split_list(text):
    return [p for p in re.split(r"[;,|]+", text) if p.strip()] if text else []


def build_activities(rows):
    nodes, index = [], {}
    for r in rows:
        line, wbs = r["_line"], r.get("wbs_id", "")
        if not wbs or not r.get("name"):
            raise ValueError(f"line {line}: WBS_ID and Name are required")
        if wbs in index:
            raise ValueError(f"line {line}: duplicate WBS_ID {wbs}")
        parts = wbs.split(".")
        parent = ".".join(parts[:-1])
        if parent and parent not in index:
            raise ValueError(f"line {line}: parent {parent} of {wbs} must appear earlier in the file")
        dur = None
        if r.get("duration"):
            f = float(r["duration"].replace(",", "."))
            if f < 0 or not f.is_integer():
                raise ValueError(f"line {line}: Duration must be a whole number of days")
            dur = int(f)
        index[wbs] = len(nodes)
        nodes.append(dict(
            line=line, wbs=wbs, indent=len(parts) - 1, parent=index.get(parent),
            name=(f"{r['id']} | {r['name']}" if r.get("id") else r["name"]),
            start=parse_date(r["start"], line) if r.get("start") else None,
            end=parse_date(r["end"], line) if r.get("end") else None,
            dur=dur, preds=split_list(r.get("predecessors", "")),
            res=[x.strip() for x in split_list(r.get("resources", ""))], children=[]))
    for i, n in enumerate(nodes):
        if n["parent"] is not None:
            nodes[n["parent"]]["children"].append(i)
    # roll up parents (children always come later in the file -> go backwards)
    for n in reversed(nodes):
        if n["children"] and n["start"] is None and n["dur"] is None and n["end"] is None:
            ch = [nodes[c] for c in n["children"]]
            n["start"] = min(c["start"] for c in ch)
            n["dur"] = (max(c["start"].toordinal() + c["dur"] for c in ch) - n["start"].toordinal())
        if n["start"] is None:
            raise ValueError(f"line {n['line']}: {n['wbs']} needs a Start date")
        if n["dur"] is None:
            if n["end"] is None:
                raise ValueError(f"line {n['line']}: {n['wbs']} needs a Duration or an End date")
            n["dur"] = (n["end"] - n["start"]).days
        if n["dur"] < 0:
            raise ValueError(f"line {n['line']}: {n['wbs']} ends before it starts")
    return nodes, index


def build_resources(res_rows, used):
    resources, indent, hier, idx = [], [], {}, {}

    def add(name, typ, parent, line="-"):
        if name in idx:
            raise ValueError(f"line {line}: duplicate resource {name}")
        i = len(resources); idx[name] = i
        if parent:
            if parent not in idx:
                raise ValueError(f"line {line}: parent '{parent}' must appear earlier in the resources file")
            hier.setdefault(idx[parent], []).append(i)
            indent.append(indent[idx[parent]] + 1)
        else:
            indent.append(0)
        resources.append([name, typ or "Human Resource", "", "", "0.0", "0.0", "0.0", ""])

    for r in res_rows:
        add(r["name"], r.get("type"), r.get("parent"), r["_line"])
    for name in used:
        if name not in idx:
            if res_rows:
                print(f"Warning: resource '{name}' is not in the resources file; added as top-level", file=sys.stderr)
            add(name, None, None)
    return resources, indent, {str(k): v for k, v in sorted(hier.items())}


def convert(rows, res_rows, time_str, stable_ids):
    nodes, index = build_activities(rows)
    succ = {i: [] for i in range(len(nodes))}
    for i, n in enumerate(nodes):
        for p in n["preds"]:
            if p not in index:
                raise ValueError(f"line {n['line']}: unknown predecessor '{p}'")
            if index[p] == i:
                raise ValueError(f"line {n['line']}: {n['wbs']} cannot be its own predecessor")
            succ[index[p]].append(i + 1)
    activities, integration = [], {}
    for i, n in enumerate(nodes):
        uid = uuid.uuid5(NS, n["wbs"]) if stable_ids else uuid.uuid4()
        activities.append([str(uid), str(i + 1), n["wbs"], n["name"],
                           ",".join(str(index[p] + 1) for p in n["preds"]),
                           f"{n['start']:%Y-%m-%d} {time_str}", "", n["dur"],
                           ",".join(str(s) for s in succ[i]), "", "", "", ""])
        if n["res"]:
            integration[str(i + 1)] = {"resources": n["res"], "risks": [], "boq": []}
    hier = {}
    for i, n in enumerate(nodes):
        if n["children"]:
            hier[str(i)] = n["children"]
    used = [r for n in nodes for r in n["res"]]
    used = list(dict.fromkeys(used))
    resources, r_indent, r_hier = build_resources(res_rows, used)
    return {"version": 3, "activities": activities, "activity_hierarchy": hier,
            "activity_indent": [n["indent"] for n in nodes],
            "resources": resources, "resource_hierarchy": r_hier, "resource_indent": r_indent,
            "risks": [], "boq": [], "integration": integration}


def main():
    ap = argparse.ArgumentParser(description="Convert a planning CSV to the planning JSON format.")
    ap.add_argument("csv_file")
    ap.add_argument("-o", "--output", help="output JSON (default: same name as the CSV)")
    ap.add_argument("--resources", help="optional resources CSV (Name, Type, Parent)")
    ap.add_argument("--time", default="00:00", help="time of day added to start dates (default 00:00)")
    ap.add_argument("--stable-ids", action="store_true", help="derive UUIDs from the WBS_ID instead of random ones")
    a = ap.parse_args()
    try:
        datetime.strptime(a.time, "%H:%M")
        rows = read_csv(a.csv_file, ACT_COLS)
        res_rows = read_csv(a.resources, RES_COLS) if a.resources else []
        out = convert(rows, res_rows, a.time, a.stable_ids)
    except (ValueError, OSError) as e:
        sys.exit(f"Error: {e}")
    path = a.output or re.sub(r"\.csv$", "", a.csv_file, flags=re.I) + ".json"
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(out, fh, indent=2, ensure_ascii=False)
    print(f"Wrote {path}: {len(out['activities'])} activities, {len(out['resources'])} resources")


if __name__ == "__main__":
    main()