import os
import json
import time
from youtube_api import get_video
from yt_parser import parse_description

DATA_DIR = os.path.join(os.path.dirname(__file__), 'data')
GRAPHS_PATH = os.path.join(DATA_DIR, 'graphs.json')

crawl_state = {
    'state': 'idle',
    'nodes': 0,
    'edges': 0,
    'root_video_id': None,
    'part2_video_id': None
}

_nodes = {}
_edges = []
_visited = set()


def reset_state():
    global crawl_state, _nodes, _edges, _visited
    crawl_state = {'state': 'idle', 'nodes': 0, 'edges': 0, 'root_video_id': None, 'part2_video_id': None}
    _nodes = {}
    _edges = []
    _visited = set()
    _write_graph()


def get_status():
    return crawl_state


def _write_graph():
    if not os.path.isdir(DATA_DIR):
        os.makedirs(DATA_DIR, exist_ok=True)
    
    root_id = crawl_state.get('root_video_id')
    part2_id = crawl_state.get('part2_video_id')
    root_title = _nodes.get(root_id, {}).get('title', root_id) if root_id else 'Unknown'
    
    # If Part 2 exists, append its title
    if part2_id and part2_id in _nodes:
        part2_title = _nodes.get(part2_id, {}).get('title', part2_id)
        root_title = f"{root_title} + {part2_title}"
    
    # Load existing graphs file
    graphs = {'graphs': {}}
    if os.path.exists(GRAPHS_PATH):
        with open(GRAPHS_PATH, 'r', encoding='utf-8') as f:
            try:
                graphs = json.load(f)
                if 'graphs' not in graphs:
                    graphs = {'graphs': {}}
            except:
                graphs = {'graphs': {}}
    
    # Add/update this graph
    if root_id:
        graphs['graphs'][root_id] = {
            'title': root_title,
            'nodes': _nodes,
            'part2_video_id': part2_id,
            'stop_video_ids': crawl_state.get('stop_video_ids', []),
            'trailer_video_id': crawl_state.get('trailer_video_id'),
            'bonus_video_ids': crawl_state.get('bonus_video_ids', []),
            'hide_bonus_button': crawl_state.get('hide_bonus_button', False)
        }
    
    # Save multi-graph format
    with open(GRAPHS_PATH, 'w', encoding='utf-8') as f:
        json.dump(graphs, f, ensure_ascii=False, indent=2)


def run_crawl(start_video_id, max_nodes=1000, part2_video_id=None, stop_video_ids=None, trailer_video_id=None, bonus_video_ids=None):
    global crawl_state, _nodes, _edges, _visited
    crawl_state['state'] = 'running'
    crawl_state['root_video_id'] = start_video_id
    crawl_state['part2_video_id'] = part2_video_id
    crawl_state['stop_video_ids'] = stop_video_ids or []
    crawl_state['trailer_video_id'] = trailer_video_id
    crawl_state['bonus_video_ids'] = bonus_video_ids or []
    
    # Fetch trailer video data if provided and not 'none'
    if trailer_video_id and trailer_video_id != 'none':
        try:
            trailer_video = get_video(trailer_video_id)
            _nodes[trailer_video_id] = {
                'title': trailer_video.get('title', trailer_video_id),
                'thumbnail': trailer_video.get('thumbnail'),
                'url': trailer_video.get('url'),
                'description': trailer_video.get('description', '')
            }
            # Add edge from trailer to root
            _edges.append({'from': trailer_video_id, 'to': start_video_id, 'label': ''})
            _visited.add(trailer_video_id)  # Mark as visited so we don't crawl it
        except Exception:
            # If trailer fetch fails, just continue without it
            pass
    
    # Fetch bonus videos (bloopers, behind the scenes, etc.)
    if bonus_video_ids:
        for bonus_id in bonus_video_ids:
            try:
                bonus_video = get_video(bonus_id)
                _nodes[bonus_id] = {
                    'title': bonus_video.get('title', bonus_id),
                    'thumbnail': bonus_video.get('thumbnail'),
                    'url': bonus_video.get('url'),
                    'description': bonus_video.get('description', '')
                }
                # Bonus videos have no connections - they're standalone
                _visited.add(bonus_id)  # Mark as visited so we don't crawl them
            except Exception:
                # If bonus fetch fails, skip it
                pass
    
    stack = [start_video_id]
    
    stop_ids_set = set(stop_video_ids or [])

    while stack:
        vid = stack.pop()
        if vid in _visited:
            continue
        try:
            video = get_video(vid)
        except Exception:
            # skip videos that error
            _visited.add(vid)
            continue

        _visited.add(vid)
        _nodes[vid] = {
            'title': video.get('title', vid),
            'thumbnail': video.get('thumbnail'),
            'url': video.get('url'),
            'description': video.get('description', '')
        }

        # Check if this is a stop node
        is_stop_node = vid in stop_ids_set
        
        choices = parse_description(video.get('description', ''))
        for c in choices:
            # Temporarily store label from parsed choice (anchor text or empty).
            _edges.append({'from': vid, 'to': c['video_id'], 'label': c.get('text', '')})
            # Only continue crawling if this is not a stop node
            if c['video_id'] not in _visited and not is_stop_node:
                stack.append(c['video_id'])

        crawl_state['nodes'] = len(_nodes)
        crawl_state['edges'] = len(_edges)
        _write_graph()

        if crawl_state['nodes'] >= max_nodes:
            break

        time.sleep(0.2)

    crawl_state['state'] = 'done'
    
    # Add choice_N fields to nodes based on ALL links found in description (not just crawled edges)
    for vid, node in _nodes.items():
        desc = node.get('description', '')
        # Re-parse description to get all video IDs
        found_choices = parse_description(desc)
        
        # Initialize outgoing and incoming lists
        node['outgoing'] = []
        node['incoming_from'] = []
        
        # Add all found choices
        for i, choice_dict in enumerate(found_choices, 1):
            choice_id = choice_dict['video_id']
            node[f'choice_{i}'] = choice_id
            # Also add choice label (title of target video if we have it)
            choice_title = _nodes.get(choice_id, {}).get('title', '')
            if not choice_title:
                # If we don't have the node, just use the video ID
                choice_title = f'Video {choice_id}'
            node[f'choice_{i}_label'] = choice_title
            
            # Add to outgoing connections
            node['outgoing'].append({
                'to': choice_id,
                'label': choice_title
            })
    
    # Build incoming connections for each node
    for vid, node in _nodes.items():
        for outgoing in node.get('outgoing', []):
            target_id = outgoing['to']
            if target_id in _nodes:
                _nodes[target_id]['incoming_from'].append({
                    'from': vid,
                    'label': node.get('title', '')
                })
    
    # Clean descriptions: extract first sentence and remove choice titles
    for vid, node in _nodes.items():
        desc = node.get('description', '')
        clean_first = ''
        if desc:
            # Split into lines first
            lines = desc.split('\n')
            cleaned_lines = []
            
            for line in lines:
                line_stripped = line.strip()
                # Skip lines that contain ► (these are choice links)
                if '►' in line:
                    continue
                # Skip empty lines
                if not line_stripped:
                    continue
                # Skip lines that look like prompts (short questions/phrases before links)
                # Common patterns: "TRY AGAIN?", "MORE?", "SHH...", etc.
                if line_stripped.endswith('?') and len(line_stripped) < 20:
                    continue
                # Skip lines that are URLs
                if line_stripped.startswith('http://') or line_stripped.startswith('https://'):
                    continue
                    
                cleaned_lines.append(line)
            
            # Rejoin cleaned lines
            first_part = '\n'.join(cleaned_lines).strip()
            
            # Get all choice labels for this node
            choice_labels = [node.get(f'choice_{i}_label', '') for i in range(1, 10) if f'choice_{i}_label' in node]
            
            # Remove lines that exactly match choice labels
            lines = first_part.split('\n')
            cleaned_lines = []
            for line in lines:
                line_stripped = line.strip()
                if line_stripped and line_stripped not in choice_labels:
                    cleaned_lines.append(line)
            
            first_part = '\n'.join(cleaned_lines).strip()
            
            # Remove appended choice titles from the end (concatenated without spaces/newlines)
            for label in choice_labels:
                if label and first_part.endswith(label):
                    first_part = first_part[:-len(label)].strip()
            
            clean_first = first_part
        
        node['clean_description'] = clean_first

    _write_graph()

