#!/usr/bin/env python3
import sys, plistlib, json, argparse
def set_key(obj, path, value):
    cur=obj
    for k in path[:-1]: cur=cur.setdefault(k, {})
    # Convert list of integers to bytes for Data fields
    if isinstance(value, list) and all(isinstance(x, int) and 0 <= x <= 255 for x in value):
        value = bytes(value)
    cur[path[-1]]=value
def ensure_array(obj, path):
    cur=obj
    for k in path[:-1]: cur=cur.setdefault(k, {})
    if path[-1] not in cur or not isinstance(cur[path[-1]], list):
        cur[path[-1]]=[]
    return cur[path[-1]]
def append_unique(obj, path, entry, key=None):
    arr=ensure_array(obj, path)
    if key is None:
        if entry not in arr: arr.append(entry)
    else:
        if not any(isinstance(x, dict) and x.get(key)==entry.get(key) for x in arr):
            arr.append(entry)
def merge_dict(obj, path, entries):
    cur=obj
    for k in path[:-1]: cur=cur.setdefault(k, {})
    tgt=cur.setdefault(path[-1], {})
    if not isinstance(tgt, dict): raise ValueError("Target not dict")
    # Convert data values before merging
    converted_entries = {}
    for key, value in entries.items():
        if isinstance(value, dict):
            # Handle nested dicts (like DeviceProperties)
            converted_dict = {}
            for nested_key, nested_value in value.items():
                if isinstance(nested_value, list) and all(isinstance(x, int) and 0 <= x <= 255 for x in nested_value):
                    converted_dict[nested_key] = bytes(nested_value)
                else:
                    converted_dict[nested_key] = nested_value
            converted_entries[key] = converted_dict
        elif isinstance(value, list) and all(isinstance(x, int) and 0 <= x <= 255 for x in value):
            converted_entries[key] = bytes(value)
        else:
            converted_entries[key] = value
    tgt.update(converted_entries)
def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("plist"); ap.add_argument("ops_json")
    a=ap.parse_args()
    data=plistlib.load(open(a.plist,"rb"))
    ops=json.loads(a.ops_json)
    for op in ops:
        t=op["op"]; path=op.get("path",[])
        if t=="set": set_key(data, path, op["value"])
        elif t=="append": append_unique(data, path, op["entry"], op.get("key"))
        elif t=="merge": merge_dict(data, path, op["entries"])
        elif t=="clear": 
            cur=data
            for k in path[:-1]: cur=cur.setdefault(k, {})
            cur[path[-1]]=[]
        elif t=="remove":
            cur=data
            for k in path[:-1]: cur=cur.get(k, {})
            arr=cur.get(path[-1], [])
            cur[path[-1]]=[x for x in arr if not (isinstance(x, dict) and x.get(op["key"])==op["value"])]
        else: raise ValueError("Unknown op "+t)
    plistlib.dump(data, open(a.plist,"wb"), sort_keys=False)
if __name__=="__main__": main()
