from flask import Flask, request, jsonify, send_from_directory
import threading
import os
import json
from crawler import run_crawl, get_status, reset_state

app = Flask(__name__)


@app.route('/crawl', methods=['POST'])
def crawl():
    data = request.get_json() or {}
    url = data.get('url') or request.form.get('url')
    part2_url = data.get('part2_url') or request.form.get('part2_url') or ''
    stop_urls = data.get('stop_urls') or request.form.get('stop_urls') or ''
    trailer_url = data.get('trailer_url') or request.form.get('trailer_url') or ''
    bonus_urls = data.get('bonus_urls') or request.form.get('bonus_urls') or ''
    
    if not url:
        return jsonify({'error': 'missing url'}), 400

    def extract_video_id(video_url):
        if 'v=' in video_url:
            return video_url.split('v=')[-1].split('&')[0]
        elif 'youtu.be/' in video_url:
            return video_url.split('youtu.be/')[-1].split('?')[0]
        return None
    
    video_id = extract_video_id(url)
    if not video_id:
        return jsonify({'error': 'unsupported url format'}), 400
    
    part2_id = extract_video_id(part2_url) if part2_url else None
    
    # Handle trailer: 'none' means explicitly no trailer, empty means allow adding later
    trailer_id = None
    if trailer_url:
        if trailer_url.lower().strip() == 'none':
            trailer_id = 'none'  # Special marker: no trailer, don't show button
        else:
            trailer_id = extract_video_id(trailer_url)
    
    # Parse stop URLs
    stop_ids = []
    if stop_urls:
        for stop_url in stop_urls.split(','):
            stop_url = stop_url.strip()
            if stop_url:
                stop_id = extract_video_id(stop_url)
                if stop_id:
                    stop_ids.append(stop_id)
    
    # Parse bonus URLs
    bonus_ids = []
    if bonus_urls:
        for bonus_url in bonus_urls.split(','):
            bonus_url = bonus_url.strip()
            if bonus_url:
                bonus_id = extract_video_id(bonus_url)
                if bonus_id:
                    bonus_ids.append(bonus_id)

    state = get_status()
    if state['state'] == 'running':
        return jsonify({'status': 'already running'}), 200

    reset_state()

    def target():
        try:
            run_crawl(video_id, part2_video_id=part2_id, stop_video_ids=stop_ids, trailer_video_id=trailer_id, bonus_video_ids=bonus_ids)
        except Exception:
            st = get_status()
            st['state'] = 'error'

    threading.Thread(target=target, daemon=True).start()

    return jsonify({'status': 'started'})


@app.route('/status', methods=['GET'])
def status():
    return jsonify(get_status())


@app.route('/video_title', methods=['GET'])
def video_title():
    video_id = request.args.get('id')
    if not video_id:
        return jsonify({'error': 'missing video id'}), 400
    
    try:
        from youtube_api import get_video
        video_data = get_video(video_id)
        if video_data and 'title' in video_data:
            return jsonify({'title': video_data['title']})
        else:
            return jsonify({'error': 'video not found'}), 404
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/add_trailer', methods=['POST'])
def add_trailer():
    data = request.get_json() or {}
    graph_id = data.get('graph_id')
    trailer_url = data.get('trailer_url')
    
    if not graph_id or not trailer_url:
        return jsonify({'error': 'missing graph_id or trailer_url'}), 400
    
    # Load graphs file
    data_dir = os.path.join(os.path.dirname(__file__), 'data')
    graphs_file = os.path.join(data_dir, 'graphs.json')
    
    if not os.path.exists(graphs_file):
        return jsonify({'error': 'no graphs found'}), 404
    
    try:
        with open(graphs_file, 'r', encoding='utf-8') as f:
            graphs = json.load(f)
        
        if graph_id not in graphs.get('graphs', {}):
            return jsonify({'error': 'graph not found'}), 404
        
        graph = graphs['graphs'][graph_id]
        
        # Check if user entered 'none' to explicitly disable trailer
        if trailer_url.lower().strip() == 'none':
            graph['trailer_video_id'] = 'none'
            # Save updated graphs
            with open(graphs_file, 'w', encoding='utf-8') as f:
                json.dump(graphs, f, ensure_ascii=False, indent=2)
            return jsonify({'status': 'success', 'trailer_id': 'none'})
        
        # Otherwise, extract video ID and fetch trailer
        def extract_video_id(video_url):
            if 'v=' in video_url:
                return video_url.split('v=')[-1].split('&')[0]
            elif 'youtu.be/' in video_url:
                return video_url.split('youtu.be/')[-1].split('?')[0]
            return None
        
        trailer_id = extract_video_id(trailer_url)
        if not trailer_id:
            return jsonify({'error': 'invalid trailer URL'}), 400
        
        # Fetch trailer video data
        from youtube_api import get_video
        trailer_video = get_video(trailer_id)
        
        description = trailer_video.get('description', '')
        
        # Clean description - remove choice links and prompts
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
        
        # Add trailer node to graph
        graph['nodes'][trailer_id] = {
            'title': trailer_video.get('title', trailer_id),
            'thumbnail': trailer_video.get('thumbnail'),
            'url': trailer_video.get('url'),
            'description': description,
            'clean_description': clean_desc,
            'outgoing': [{'to': graph_id, 'label': ''}],
            'incoming_from': []
        }
        
        # Set trailer_video_id
        graph['trailer_video_id'] = trailer_id
        
        # Save updated graphs
        with open(graphs_file, 'w', encoding='utf-8') as f:
            json.dump(graphs, f, ensure_ascii=False, indent=2)
        
        return jsonify({'status': 'success', 'trailer_id': trailer_id})
    
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/add_bonus', methods=['POST'])
def add_bonus():
    data = request.get_json() or {}
    graph_id = data.get('graph_id')
    bonus_urls = data.get('bonus_urls')
    
    if not graph_id or not bonus_urls:
        return jsonify({'error': 'missing graph_id or bonus_urls'}), 400
    
    # Load graphs file
    data_dir = os.path.join(os.path.dirname(__file__), 'data')
    graphs_file = os.path.join(data_dir, 'graphs.json')
    
    if not os.path.exists(graphs_file):
        return jsonify({'error': 'no graphs found'}), 404
    
    try:
        with open(graphs_file, 'r', encoding='utf-8') as f:
            graphs = json.load(f)
        
        if graph_id not in graphs.get('graphs', {}):
            return jsonify({'error': 'graph not found'}), 404
        
        graph = graphs['graphs'][graph_id]
        
        # Parse bonus URLs
        def extract_video_id(video_url):
            if 'v=' in video_url:
                return video_url.split('v=')[-1].split('&')[0]
            elif 'youtu.be/' in video_url:
                return video_url.split('youtu.be/')[-1].split('?')[0]
            return None
        
        bonus_ids = []
        for bonus_url in bonus_urls.split(','):
            bonus_url = bonus_url.strip()
            if bonus_url:
                bonus_id = extract_video_id(bonus_url)
                if bonus_id:
                    bonus_ids.append(bonus_id)
        
        if not bonus_ids:
            return jsonify({'error': 'no valid bonus URLs'}), 400
        
        # Fetch and add bonus videos
        from youtube_api import get_video
        for bonus_id in bonus_ids:
            try:
                bonus_video = get_video(bonus_id)
                description = bonus_video.get('description', '')
                
                # Clean description - remove choice links and prompts
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
                
                graph['nodes'][bonus_id] = {
                    'title': bonus_video.get('title', bonus_id),
                    'thumbnail': bonus_video.get('thumbnail'),
                    'url': bonus_video.get('url'),
                    'description': description,
                    'clean_description': clean_desc,
                    'outgoing': [],
                    'incoming_from': []
                }
            except Exception:
                # Skip if fetch fails
                pass
        
        # Update bonus_video_ids list
        if 'bonus_video_ids' not in graph:
            graph['bonus_video_ids'] = []
        graph['bonus_video_ids'].extend(bonus_ids)
        
        # Save updated graphs
        with open(graphs_file, 'w', encoding='utf-8') as f:
            json.dump(graphs, f, ensure_ascii=False, indent=2)
        
        return jsonify({'status': 'success', 'bonus_ids': bonus_ids})
    
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/toggle_bonus_button', methods=['POST'])
def toggle_bonus_button():
    data = request.get_json() or {}
    graph_id = data.get('graph_id')
    hide = data.get('hide', True)
    
    if not graph_id:
        return jsonify({'error': 'missing graph_id'}), 400
    
    # Load graphs file
    data_dir = os.path.join(os.path.dirname(__file__), 'data')
    graphs_file = os.path.join(data_dir, 'graphs.json')
    
    if not os.path.exists(graphs_file):
        return jsonify({'error': 'no graphs found'}), 404
    
    try:
        with open(graphs_file, 'r', encoding='utf-8') as f:
            graphs = json.load(f)
        
        if graph_id not in graphs.get('graphs', {}):
            return jsonify({'error': 'graph not found'}), 404
        
        graph = graphs['graphs'][graph_id]
        graph['hide_bonus_button'] = hide
        
        # Save updated graphs
        with open(graphs_file, 'w', encoding='utf-8') as f:
            json.dump(graphs, f, ensure_ascii=False, indent=2)
        
        return jsonify({'status': 'success', 'hide_bonus_button': hide})
    
    except Exception as e:
        return jsonify({'error': str(e)}), 500
        if video_data and 'title' in video_data:
            return jsonify({'title': video_data['title']})
        else:
            return jsonify({'error': 'video not found'}), 404
    


@app.route('/graph', methods=['GET'])
def graph():
    data_dir = os.path.join(os.path.dirname(__file__), 'data')
    graphs_file = os.path.join(data_dir, 'graphs.json')
    
    if os.path.exists(graphs_file):
        return send_from_directory(data_dir, 'graphs.json')
    else:
        # No graphs found - return empty structure
        return jsonify({'graphs': {}})


@app.route('/frontend/<path:filename>', methods=['GET'])
def frontend_file(filename):
    # serve frontend files placed in the workspace/frontend folder
    frontend_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'frontend'))
    return send_from_directory(frontend_dir, filename)


@app.route('/static/<path:filename>', methods=['GET'])
def static_file(filename):
    # Serve frontend static files (styles, js) at /static/*
    frontend_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'frontend'))
    return send_from_directory(frontend_dir, filename)


@app.route('/', methods=['GET'])
def root_index():
    frontend_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'frontend'))
    return send_from_directory(frontend_dir, 'input.html')


@app.route('/index.html', methods=['GET'])
def index_html():
    frontend_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'frontend'))
    return send_from_directory(frontend_dir, 'input.html')


if __name__ == '__main__':
    app.run(debug=True, port=5000)
