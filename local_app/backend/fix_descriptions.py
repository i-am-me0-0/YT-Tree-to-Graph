"""
Script to add clean_description to trailer and bonus videos in existing graphs.
Run this once to fix old data that doesn't have clean_description.
"""
import json
import os


def clean_description(description):
    """Clean description by removing choice links and prompts"""
    clean_desc = ''
    if description:
        lines = description.split('\n')
        cleaned_lines = []
        
        for line in lines:
            line_stripped = line.strip()
            # Skip lines with choice markers
            if '►' in line:
                continue
            # Skip empty lines
            if not line_stripped:
                continue
            # Skip short questions (prompts)
            if line_stripped.endswith('?') and len(line_stripped) < 20:
                continue
            # Skip URLs
            if line_stripped.startswith('http://') or line_stripped.startswith('https://'):
                continue
            cleaned_lines.append(line)
        
        clean_desc = '\n'.join(cleaned_lines).strip()
    
    return clean_desc


def main():
    data_dir = os.path.join(os.path.dirname(__file__), 'data')
    graphs_file = os.path.join(data_dir, 'graphs.json')
    
    if not os.path.exists(graphs_file):
        print('graphs.json not found')
        return
    
    with open(graphs_file, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    updated_count = 0
    
    for graph_id, graph in data.get('graphs', {}).items():
        trailer_id = graph.get('trailer_video_id')
        bonus_ids = graph.get('bonus_video_ids', [])
        
        # Update trailer node
        if trailer_id and trailer_id != 'none':
            if trailer_id in graph.get('nodes', {}):
                node = graph['nodes'][trailer_id]
                if 'clean_description' not in node:
                    desc = node.get('description', '')
                    node['clean_description'] = clean_description(desc)
                    updated_count += 1
                    print(f'Updated trailer {trailer_id} in graph {graph_id}')
        
        # Update bonus nodes
        for bonus_id in bonus_ids:
            if bonus_id in graph.get('nodes', {}):
                node = graph['nodes'][bonus_id]
                if 'clean_description' not in node:
                    desc = node.get('description', '')
                    node['clean_description'] = clean_description(desc)
                    updated_count += 1
                    print(f'Updated bonus {bonus_id} in graph {graph_id}')
    
    if updated_count > 0:
        # Save updated data
        with open(graphs_file, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        print(f'\nSuccessfully updated {updated_count} nodes')
    else:
        print('No nodes needed updating')


if __name__ == '__main__':
    main()
