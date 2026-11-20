"""Audited per-rule attention eligibility; keep in sync with Ghost core/findings.hpp."""
PRIORITY_POLICY='recon-priority-v2-audited18'
STRONG_RULES=('WIFI-FLOCK-COR-1','WIFI-AXON-COR-1','BLE-AXON-BWC-1','BLE-FLOCK-NAME-COR-1','BLE-FINDMY-FRAME-1','BLE-FHN-FRAME-1','BLE-TILE-DATA-1','BLE-SMARTTAG-DATA-1','BLE-CHIPOLO-DATA-1','BLE-DULT-DATA-1')
REPORT_RULES=STRONG_RULES+('BLE-SKIMMER-HC-NAME-1','WIFI-DISCONNECT-BURST-1','WIFI-SECURITY-MISMATCH-1','RID-MESSAGE-1','BLE-FLIPPER-SVC-1','BLE-META-COR-1','BEHAVIOR-ACTIVITY-BURST-1','BEHAVIOR-SECURITY-CHANGE-1')
def priority(signature,supported):
    if not supported:return 0
    rule=signature.get('rule');strength=signature.get('confidence',0)
    if rule=='BEHAVIOR-ACTIVITY-BURST-1' and strength>=60:return 40
    return 60 if rule in REPORT_RULES and strength>=80 else 15
