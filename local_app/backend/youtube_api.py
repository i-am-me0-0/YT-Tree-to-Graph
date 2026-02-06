import requests
import re
import html


def get_video(video_id, session=None):
    s = session or requests
    url = f'https://www.youtube.com/watch?v={video_id}'
    # Try oEmbed for title/thumbnail, then fetch page for description
    title = None
    thumbnail = f'https://i.ytimg.com/vi/{video_id}/maxresdefault.jpg'
    description = ''

    try:
        oembed = s.get('https://www.youtube.com/oembed', params={'url': url, 'format': 'json'}, timeout=10)
        if oembed.ok:
            data = oembed.json()
            title = data.get('title')
            if title:
                title = html.unescape(title)
    except Exception:
        pass

    try:
        r = s.get(url, timeout=10)
        if r.ok:
            # Extract description with URLs from ytInitialData
            # Look for the description with commandRuns which contains the actual links
            initial_data_match = re.search(r'var ytInitialData = ({.*?});', r.text)
            if initial_data_match:
                try:
                    import json
                    data = json.loads(initial_data_match.group(1))
                    
                    # Navigate to video secondary info renderer for description
                    contents = data.get('contents', {})
                    two_col = contents.get('twoColumnWatchNextResults', {})
                    results = two_col.get('results', {}).get('results', {})
                    contents_list = results.get('contents', [])
                    
                    for content in contents_list:
                        video_secondary = content.get('videoSecondaryInfoRenderer', {})
                        if 'attributedDescription' in video_secondary:
                            desc_data = video_secondary['attributedDescription']
                            
                            # Build description with HTML links from commandRuns
                            if 'content' in desc_data:
                                desc_parts = []
                                content_text = desc_data.get('content', '')
                                command_runs = desc_data.get('commandRuns', [])
                                
                                if command_runs:
                                    # Reconstruct with links
                                    last_end = 0
                                    for run in command_runs:
                                        start_index = run.get('startIndex', 0)
                                        length = run.get('length', 0)
                                        
                                        # Add text before this link
                                        if start_index > last_end:
                                            desc_parts.append(content_text[last_end:start_index])
                                        
                                        # Extract URL from command
                                        command = run.get('onTap', {}).get('innertubeCommand', {})
                                        url_endpoint = command.get('commandMetadata', {}).get('webCommandMetadata', {}).get('url', '')
                                        
                                        link_text = content_text[start_index:start_index + length]
                                        
                                        if url_endpoint:
                                            # Convert to full URL if needed
                                            if url_endpoint.startswith('/'):
                                                url_endpoint = f'https://www.youtube.com{url_endpoint}'
                                            desc_parts.append(f'<a href="{url_endpoint}">{link_text}</a>')
                                        else:
                                            desc_parts.append(link_text)
                                        
                                        last_end = start_index + length
                                    
                                    # Add remaining text
                                    if last_end < len(content_text):
                                        desc_parts.append(content_text[last_end:])
                                    
                                    description = ''.join(desc_parts)
                                else:
                                    # No links, just use content
                                    description = content_text
                                
                                break
                except Exception as e:
                    pass
            
            # Fallback to og:description or meta name=description
            if not description:
                m = re.search(r'<meta property="og:description" content="([^"]*)"', r.text)
                if not m:
                    m = re.search(r'<meta name="description" content="([^"]*)"', r.text)
                if m:
                    description = html.unescape(m.group(1)).strip()
            
            # sometimes title tag is available
            if not title:
                mt = re.search(r'<title>(.*?)</title>', r.text, re.I | re.S)
                if mt:
                    title = html.unescape(mt.group(1).replace(' - YouTube', '').strip())
    except Exception:
        pass

    return {'title': title or video_id, 'description': description, 'thumbnail': thumbnail, 'url': url}
