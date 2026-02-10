#!/usr/bin/env python3
import json
import os
import sys

p = os.path.join(os.getcwd(), 'docs', 'graphs.json')
if not os.path.exists(p):
    print(json.dumps({'error': f'file not found: {p}'}))
    sys.exit(2)

with open(p, 'r', encoding='utf-8') as f:
    data = json.load(f)

report = {
    'graphs_examined': 0,
    'missing_outgoing_targets': [],
    'outgoing_not_in_incoming': [],
    'incoming_from_missing': [],
    'empty_outgoing_labels': [],
    'empty_incoming_labels': [],
    'description_no_clean': [],
}

for graph_id, graph in data.items():
    report['graphs_examined'] += 1
    nodes = graph.get('nodes') or {}
    node_ids = set(nodes.keys())
    for node_id, node in nodes.items():
        # outgoing checks
        for out in node.get('outgoing', []):
            to = out.get('to') if isinstance(out, dict) else None
            label = out.get('label') if isinstance(out, dict) else None
            if to is None:
                report['missing_outgoing_targets'].append({'graph': graph_id, 'from': node_id, 'edge': out})
                continue
            if to not in node_ids:
                report['missing_outgoing_targets'].append({'graph': graph_id, 'from': node_id, 'to': to})
            else:
                target_node = nodes[to]
                incoming = target_node.get('incoming_from', [])
                found = any(inc.get('from') == node_id for inc in incoming if isinstance(inc, dict))
                if not found:
                    report['outgoing_not_in_incoming'].append({'graph': graph_id, 'from': node_id, 'to': to})
            # label checks
            if isinstance(label, str):
                if label.strip() == '':
                    report['empty_outgoing_labels'].append({'graph': graph_id, 'from': node_id, 'to': to, 'label': label})
            else:
                report['empty_outgoing_labels'].append({'graph': graph_id, 'from': node_id, 'to': to, 'label': label})
        # incoming checks that reference missing sources
        for inc in node.get('incoming_from', []):
            if not isinstance(inc, dict):
                report['incoming_from_missing'].append({'graph': graph_id, 'to': node_id, 'from': inc})
                continue
            frm = inc.get('from')
            label = inc.get('label')
            if frm not in node_ids:
                report['incoming_from_missing'].append({'graph': graph_id, 'to': node_id, 'from': frm})
            if isinstance(label, str) and label.strip() == '':
                report['empty_incoming_labels'].append({'graph': graph_id, 'to': node_id, 'from': frm, 'label': label})
            elif not isinstance(label, str):
                report['empty_incoming_labels'].append({'graph': graph_id, 'to': node_id, 'from': frm, 'label': label})
        # description / clean_description
        if node.get('description') and not node.get('clean_description'):
            report['description_no_clean'].append({'graph': graph_id, 'node': node_id})

# counts
for k in ['missing_outgoing_targets','outgoing_not_in_incoming','incoming_from_missing','empty_outgoing_labels','empty_incoming_labels','description_no_clean']:
    report[k + '_count'] = len(report[k])

print(json.dumps(report, ensure_ascii=False, indent=2))
