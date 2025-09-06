#!/usr/bin/env python3.11
import sys, plistlib, json, argparse
def set_key(obj, path, value):
    cur=obj
    for k in path[:-1]: cur=cur.setdefault(k, {})
    # Convert list of integers to bytes for Data fields
    # Handle empty arrays and arrays with integers
    if isinstance(value, list):
        if all(isinstance(x, int) and 0 <= x <= 255 for x in value):
            value = bytes(value)
        elif len(value) == 0:
            # Empty array should become empty bytes for data fields
            # Check if this is a data field by the key name
            field_name = path[-1] if path else ""
            if field_name in ["Find", "Mask", "Replace", "ReplaceMask", "Cpuid1Data", "Cpuid1Mask"]:
                value = bytes()
    cur[path[-1]]=value
def ensure_array(obj, path):
    cur=obj
    for k in path[:-1]: cur=cur.setdefault(k, {})
    if path[-1] not in cur or not isinstance(cur[path[-1]], list):
        cur[path[-1]]=[]
    return cur[path[-1]]
def append_unique(obj, path, entry, key=None):
    # Convert data values in entry before appending
    if isinstance(entry, dict):
        entry = convert_data_values_dict(entry)
    arr=ensure_array(obj, path)
    if key is None:
        if entry not in arr: arr.append(entry)
    else:
        if not any(isinstance(x, dict) and x.get(key)==entry.get(key) for x in arr):
            arr.append(entry)

def convert_data_values_dict(d):
    """Convert data values in a dictionary recursively"""
    if not isinstance(d, dict):
        return d
    
    converted = {}
    for key, value in d.items():
        if isinstance(value, list):
            # For kernel patch data fields, always convert to bytes
            if key in ["Find", "Mask", "Replace", "ReplaceMask", "Cpuid1Data", "Cpuid1Mask"]:
                converted[key] = bytes(value)
            elif all(isinstance(x, int) and 0 <= x <= 255 for x in value):
                converted[key] = bytes(value)
            else:
                converted[key] = value
        elif isinstance(value, dict):
            converted[key] = convert_data_values_dict(value)
        else:
            converted[key] = value
    return converted
def merge_dict(obj, path, entries):
    cur=obj
    for k in path[:-1]: cur=cur.setdefault(k, {})
    tgt=cur.setdefault(path[-1], {})
    if not isinstance(tgt, dict): raise ValueError("Target not dict")
    # Convert data values before merging
    converted_entries = convert_data_values_dict(entries)
    tgt.update(converted_entries)

if __name__ == "__main__":
    a=argparse.ArgumentParser()
    a.add_argument("plist")
    a.add_argument("ops_json")
    a=a.parse_args()
    ops=json.loads(a.ops_json)
    data=plistlib.load(open(a.plist,"rb"))
    for op in ops:
        t=op["op"]
        path=op["path"]
        if t=="set": set_key(data, path, op["value"])
        elif t=="append": append_unique(data, path, op["entry"], op.get("key"))
        elif t=="merge": merge_dict(data, path, op["entries"])
        elif t=="delete":
            cur=data
            for k in path[:-1]: cur=cur[k]
            del cur[path[-1]]
        elif t=="list":
            cur=data
            for k in path: cur=cur[k]
            print(f"{k}: {cur}")
    plistlib.dump(data, open(a.plist,"wb"), sort_keys=False)
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
