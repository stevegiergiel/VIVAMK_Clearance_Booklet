@echo off
python build_booklet_with_id.py --config configs\christmas.json --state-file monitor_state\christmas.json
python build_booklet_with_id.py --config configs\mega_sale.json --state-file monitor_state\mega_sale.json
python build_booklet_with_id.py --config configs\pets.json --state-file monitor_state\pets.json
python build_booklet_with_id.py --config configs\personalised.json --state-file monitor_state\personalised.json
python build_booklet_with_id.py --config configs\winter_warmers.json --state-file monitor_state\winter_warmers.json
pause
