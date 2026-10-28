#!/usr/bin/env python3
"""Offline regression test for table cells and image-alt mission rewards."""
import importlib.util
from pathlib import Path
script=Path(__file__).with_name("update_missions.py")
spec=importlib.util.spec_from_file_location("update_missions", script)
mod=importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)
html='''<table><tr><th>PL</th><th>Mission / Zone</th><th>Alert Reward</th></tr><tr><td>58</td><td><img alt="Fight the Storm"> Canny Valley · The City</td><td><img alt="V-Bucks ×50"> Founders only</td></tr></table>'''
parser=mod.TextExtractor(); parser.feed(html)
text="".join(parser.parts)
rows=mod.extract_missions(text,"Test source")
assert len(rows)==1, f"Expected one mission row, got {rows!r}; extracted text={text!r}"
assert rows[0]["zone"]=="Canny Valley", rows
assert rows[0]["vbucks"]==50, rows
print("PASS: extracted one Canny Valley mission with 50 V-Bucks from HTML table/image labels.")
