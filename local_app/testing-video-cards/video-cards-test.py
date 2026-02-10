#!/usr/bin/env python3
"""
Batch YouTube Card Data Extractor
Automatically extracts card timing and position data from YouTube videos
"""

import json
import time
import sys
import os
import re
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.by import By

# JavaScript to extract card data from the page
EXTRACT_SCRIPT = """
function extractCardData() {
    try {
        let playerResponse = window.ytInitialPlayerResponse;
        
        if (!playerResponse) {
            const scripts = document.querySelectorAll('script');
            for (let script of scripts) {
                const content = script.textContent;
                if (content.includes('ytInitialPlayerResponse')) {
                    const match = content.match(/ytInitialPlayerResponse\\s*=\\s*({.+?});/);
                    if (match) {
                        playerResponse = JSON.parse(match[1]);
                        break;
                    }
                }
            }
        }
        
        if (!playerResponse) {
            return { error: 'No player data found' };
        }
        
        const result = {
            videoId: playerResponse.videoDetails?.videoId,
            title: playerResponse.videoDetails?.title,
            lengthSeconds: playerResponse.videoDetails?.lengthSeconds,
            description: playerResponse.videoDetails?.shortDescription || '',
            endscreen: []
        };
        
        
        
        // Extract endscreen elements
        if (playerResponse.endscreen?.endscreenRenderer?.elements) {
            result.endscreen = playerResponse.endscreen.endscreenRenderer.elements.map(element => {
                const renderer = element.endscreenElementRenderer;
                if (!renderer) return null;
                
                return {
                    style: renderer.style,
                    startMs: renderer.startMs,
                    endMs: renderer.endMs,
                    left: renderer.left,
                    top: renderer.top,
                    width: renderer.width,
                    aspectRatio: renderer.aspectRatio,
                    title: renderer.title?.simpleText || '',
                    metadata: renderer.metadata?.simpleText || '',
                    targetId: renderer.endpoint?.watchEndpoint?.videoId || 
                             renderer.endpoint?.urlEndpoint?.url || null
                };
            }).filter(e => e !== null);
        }
        
        return result;
    } catch (error) {
        return { error: error.toString() };
    }
}

return extractCardData();
"""

def setup_driver(headless=True):
    """Setup Chrome WebDriver with appropriate options"""
    chrome_options = Options()
    
    if headless:
        chrome_options.add_argument('--headless=new')
    
    chrome_options.add_argument('--no-sandbox')
    chrome_options.add_argument('--disable-dev-shm-usage')
    chrome_options.add_argument('--disable-blink-features=AutomationControlled')
    # Allow autoplay so we can mute/play programmatically
    chrome_options.add_argument('--autoplay-policy=no-user-gesture-required')
    # Mute audio at the browser level so tabs start muted immediately
    chrome_options.add_argument('--mute-audio')
    # Use eager page load to speed things up
    try:
        chrome_options.page_load_strategy = 'eager'
    except Exception:
        pass
    
    # Force English language
    chrome_options.add_argument('--lang=en-US')
    chrome_options.add_experimental_option('prefs', {
        'intl.accept_languages': 'en-US,en'
    })
    
    chrome_options.add_argument('--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36')
    
    # Ad blocking via preferences
    chrome_options.add_argument('--disable-popup-blocking')
    chrome_options.add_experimental_option('prefs', {
        'intl.accept_languages': 'en-US,en',
        'profile.default_content_setting_values.notifications': 2,
        'profile.default_content_settings.popups': 0,
        # Disable images to reduce bandwidth and speed up loading
        'profile.managed_default_content_settings.images': 2
    })
    
    # Disable logging
    chrome_options.add_experimental_option('excludeSwitches', ['enable-logging'])
    
    driver = webdriver.Chrome(options=chrome_options)
    
    # Set YouTube language cookie
    driver.get('https://www.youtube.com')
    driver.add_cookie({
        'name': 'PREF',
        'value': 'f1=50000000&hl=en',
        'domain': '.youtube.com'
    })
    
    return driver

def load_graph_info(json_file):
    """Load graphs.json and return existing node ids and referenced ids (outgoing/incoming)
    Returns (set(existing_node_ids), set(referenced_ids))
    """
    try:
        with open(json_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
    except FileNotFoundError:
        print(f"Error: File '{json_file}' not found")
        return set(), set()
    except json.JSONDecodeError:
        print(f"Error: Invalid JSON in '{json_file}'")
        return set(), set()

    existing = set()
    referenced = set()

    for graph_key, graph_data in data.get('graphs', {}).items():
        nodes = graph_data.get('nodes', {})
        for node_id, node_data in nodes.items():
            existing.add(node_id)

            # collect outgoing 'to' ids
            for out in node_data.get('outgoing', []):
                to = out.get('to')
                if to:
                    referenced.add(to)

            # collect incoming 'from' ids
            for inc in node_data.get('incoming_from', []):
                fr = inc.get('from')
                if fr:
                    referenced.add(fr)

    return existing, referenced

def load_existing_card_data(json_file):
    try:
        with open(json_file, 'r', encoding='utf-8') as f:
            return json.load(f)
    except FileNotFoundError:
        return {}
    except json.JSONDecodeError:
        return {}

def extract_video_data(driver, video_id, delay=3):
    """Extract card data from a single video"""
    url = f"https://www.youtube.com/watch?v={video_id}"
    
    try:
        print(f"  Loading {video_id}...", end=' ', flush=True)
        driver.get(url)
        
        # Handle cookie consent popup (if it appears)
        try:
            # Try multiple possible cookie consent button selectors
            consent_selectors = [
                "button[aria-label*='Accept']",
                "button[aria-label*='accept']",
                "button.yt-spec-button-shape-next--filled",
                "ytd-button-renderer button"
            ]
            for selector in consent_selectors:
                try:
                    consent_button = WebDriverWait(driver, 2).until(
                        EC.element_to_be_clickable((By.CSS_SELECTOR, selector))
                    )
                    aria_label = consent_button.get_attribute('aria-label')
                    if 'accept' in consent_button.text.lower() or (aria_label and 'accept' in aria_label.lower()):
                        consent_button.click()
                        time.sleep(1)
                        break
                except:
                    continue
        except:
            pass  # No consent popup or already accepted
        
        # Wait for page to load the player if not present
        try:
            WebDriverWait(driver, 10).until(
                EC.presence_of_element_located((By.ID, "movie_player"))
            )
        except Exception:
            pass
        
        # Try to skip ads if present
        try:
            skip_button_selectors = [
                ".ytp-ad-skip-button",
                ".ytp-skip-ad-button",
                "button.ytp-ad-skip-button-modern"
            ]
            for selector in skip_button_selectors:
                try:
                    skip_button = WebDriverWait(driver, 2).until(
                        EC.element_to_be_clickable((By.CSS_SELECTOR, selector))
                    )
                    skip_button.click()
                    time.sleep(0.5)
                    break
                except:
                    continue
        except:
            pass  # No ads or already skipped
        
        # Additional wait for JavaScript to fully load
        time.sleep(delay)
        
        # Execute extraction script
        data = driver.execute_script(EXTRACT_SCRIPT)
        
        if 'error' in data:
            print(f"❌ Error: {data['error']}")
            return None
        
        # Count items found
        endscreen_count = len(data.get('endscreen', []))
        print(f"✓ Found {endscreen_count} endscreen elements")

        
        return data
        
    except Exception as e:
        print(f"❌ Failed: {str(e)}")
        return None

def load_existing_videos(json_file):
    """Load video IDs from existing graphs.json"""
    try:
        with open(json_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        video_ids = []
        
        # Extract all unique video IDs from the graph
        for graph_key, graph_data in data.get('graphs', {}).items():
            for node_id, node_data in graph_data.get('nodes', {}).items():
                if node_id not in video_ids:
                    video_ids.append(node_id)
        
        return video_ids
    
    except FileNotFoundError:
        print(f"Error: File '{json_file}' not found")
        return []
    except json.JSONDecodeError:
        print(f"Error: Invalid JSON in '{json_file}'")
        return []


def clean_text_for_storage(text: str) -> str:
    """Match backend.clean_description: remove choice links, short prompts, URLs, and skip empty lines.

    Keeps meaningful newlines between retained lines.
    """
    if not text:
        return ''
    # normalize line endings
    s = text.replace('\r\n', '\n').replace('\r', '\n')
    # remove simple HTML tags
    s = re.sub(r'<[^>]+>', '', s)
    lines = s.split('\n')
    cleaned_lines = []
    for line in lines:
        line_stripped = line.strip()
        if not line_stripped:
            continue
        # Skip lines with choice markers
        if '►' in line_stripped:
            continue
        # Skip short questions (prompts)
        if line_stripped.endswith('?') and len(line_stripped) < 20:
            continue
        # Skip URLs-only lines
        if line_stripped.startswith('http://') or line_stripped.startswith('https://'):
            continue
        cleaned_lines.append(line_stripped)

    return '\n'.join(cleaned_lines).strip()

def main():
    # Configuration
    # Prefer backend data file when available so updates go to the canonical store
    default_backend = os.path.normpath(os.path.join(os.path.dirname(__file__), '..', 'backend', 'data', 'graphs.json'))
    INPUT_FILE =  default_backend if os.path.exists(default_backend) else 'graphs.json'
    HEADLESS = False  # Set to False to see the browser
    DELAY_BETWEEN_VIDEOS = 1  # Seconds to wait for each page to load
    MAX_VIDEOS = 0  # 0 = process all missing; >0 = limit to that many videos
    
    print("=" * 60)
    print("YouTube Card Data Batch Extractor")
    print("=" * 60)
    
    # Load graph info and existing extracted card data
    print(f"\n📂 Loading graph info from {INPUT_FILE}...")
    existing_nodes, referenced_ids = load_graph_info(INPUT_FILE)

    # Load full graphs JSON so we can check which nodes already have card data
    try:
        with open(INPUT_FILE, 'r', encoding='utf-8') as f:
            graphs_json = json.load(f)
    except Exception:
        graphs_json = {"graphs": {}}

    # Videos that exist as nodes but missing extracted card data
    nodes_missing_cards = []
    for gkey, gdata in graphs_json.get('graphs', {}).items():
        for node_id, node_data in gdata.get('nodes', {}).items():
            if node_id in existing_nodes:
                if not node_data.get('card_data'):
                    nodes_missing_cards.append(node_id)

    # Videos referenced in outgoing/incoming but missing as full nodes
    missing_nodes = list(referenced_ids - existing_nodes)

    # Prepare list: prioritize completely missing nodes, then nodes missing cards
    to_process = missing_nodes + [v for v in nodes_missing_cards if v not in missing_nodes]

    if not to_process:
        print("❌ No missing videos or missing card data found. Exiting.")
        return

    if MAX_VIDEOS > 0:
        to_process = to_process[:MAX_VIDEOS]

    print(f"✓ Found {len(to_process)} videos to process (missing: {len(missing_nodes)}, missing_cards: {len(nodes_missing_cards)})")
    
    # Setup browser
    print("\n🌐 Starting Chrome browser...")
    driver = setup_driver(headless=HEADLESS)
    
    # Extract data from all videos
    results = {}
    successful = 0
    failed = 0
    
    print(f"\n📹 Processing {len(to_process)} videos...\n")
    
    # Attempt to import backend crawler to run crawl logic for new nodes
    crawler = None
    crawled_targets = set()
    try:
        backend_dir = os.path.normpath(os.path.join(os.path.dirname(__file__), '..', 'backend'))
        if backend_dir not in sys.path:
            sys.path.insert(0, backend_dir)
        import crawler as backend_crawler
        crawler = backend_crawler
    except Exception:
        crawler = None

    # container graph key to add new nodes into (use first graph available)
    container_graph_key = next(iter(graphs_json.get('graphs', {})), None)

    for i, video_id in enumerate(to_process, 1):
        print(f"[{i}/{len(to_process)}]", end=' ')

        data = extract_video_data(driver, video_id, delay=DELAY_BETWEEN_VIDEOS)
        
        if data:
            results[video_id] = data
            successful += 1
            # Update graphs.json structure: add node if missing, add outgoing/incoming edges
            try:
                elements = data.get('endscreen', [])
                # ensure container exists
                if container_graph_key is None:
                    container_graph_key = video_id
                    graphs_json.setdefault('graphs', {}).setdefault(container_graph_key, {'title': '', 'nodes': {}})

                nodes = graphs_json['graphs'][container_graph_key].setdefault('nodes', {})

                # add current node if missing; overwrite only when suspiciously empty
                node = nodes.setdefault(video_id, {})
                # fill title if empty
                if not node.get('title'):
                    node['title'] = data.get('title') or ''
                node.setdefault('thumbnail', f"https://i.ytimg.com/vi/{video_id}/maxresdefault.jpg")
                node.setdefault('url', f"https://www.youtube.com/watch?v={video_id}")
                # fill description if empty using extracted full description
                if not node.get('description'):
                    node['description'] = data.get('description') or ''
                node.setdefault('outgoing', [])
                node.setdefault('incoming_from', [])
                # set clean_description if missing
                if not node.get('clean_description'):
                    desc = data.get('description') or ''
                    node['clean_description'] = clean_text_for_storage(desc) if desc else ''
                # attach card data
                node.setdefault('card_data', {})

                # process outgoing targets
                for el in elements:
                    target = el.get('targetId')
                    if not target:
                        continue

                    # ensure target node exists; if not, create minimal
                    target_node = nodes.setdefault(target, {})
                    target_node.setdefault('title', '')
                    target_node.setdefault('thumbnail', f"https://i.ytimg.com/vi/{target}/maxresdefault.jpg")
                    target_node.setdefault('url', f"https://www.youtube.com/watch?v={target}")
                    target_node.setdefault('description', '')
                    target_node.setdefault('outgoing', [])
                    target_node.setdefault('incoming_from', [])

                    # If the endscreen provided a title, use it when the target's title is empty
                    try:
                        el_title = el.get('title')
                        if el_title and not target_node.get('title'):
                            target_node['title'] = el_title
                    except Exception:
                        pass

                    # Add element metadata onto the target node itself (only once)
                    try:
                        meta = el.get('metadata')
                        if meta and not target_node.get('card_metadata'):
                            target_node['card_metadata'] = meta
                    except Exception:
                        pass

                    # add outgoing entry on current node (label = target video's title when available)
                    try:
                        outgoing_label = target_node.get('title') or el.get('title') or el.get('metadata') or ''
                        if not any(o.get('to') == target for o in node.get('outgoing', [])):
                            node['outgoing'].append({'to': target, 'label': outgoing_label})
                    except Exception:
                        pass

                    # If this target was one of the missing nodes, invoke crawler to populate it (once)
                    try:
                        if crawler and target in missing_nodes and target not in crawled_targets:
                            print(f"\nInvoking crawler.run_crawl for {target}...", end=' ')
                            try:
                                crawler.run_crawl(target, max_nodes=10)
                                crawled_targets.add(target)
                                print("done")
                            except Exception as e:
                                print(f"failed: {e}")
                    except Exception:
                        pass

                    # add incoming entry to target (label = source video's title)
                    try:
                        incoming_label = node.get('title') or data.get('title') or ''
                        if not any(inc.get('from') == video_id for inc in target_node.get('incoming_from', [])):
                            target_node['incoming_from'].append({'from': video_id, 'label': incoming_label})
                    except Exception:
                        pass

                # attach cleaned card data to current node only if missing (avoid duplicate overwrite)
                if data and not node.get('card_data'):
                    try:
                        cleaned = {}
                        cleaned['endscreen'] = []
                        for el in data.get('endscreen', []):
                            # keep only the essential layout/timing fields
                            keep = ['aspectRatio', 'endMs', 'left', 'startMs', 'targetId', 'top', 'width']
                            new_el = {k: el.get(k) for k in keep if el.get(k) is not None}
                            if new_el:
                                cleaned['endscreen'].append(new_el)
                        if data.get('lengthSeconds') is not None:
                            cleaned['lengthSeconds'] = data.get('lengthSeconds')
                        node['card_data'] = cleaned
                    except Exception:
                        node['card_data'] = {}
            except Exception as e:
                print(f"\nWarning updating graphs.json: {e}")
        else:
            failed += 1
        
        # Small delay between requests to be polite
        time.sleep(0.5)
    
    # Close browser
    driver.quit()
    
    # Backfill any missing metadata on nodes for videos we just scraped
    try:
        for vid, data in results.items():
            for gkey, gdata in graphs_json.get('graphs', {}).items():
                node = gdata.get('nodes', {}).get(vid)
                if not node:
                    continue
                # title
                if not node.get('title'):
                    node['title'] = data.get('title') or ''
                # thumbnail/url
                if not node.get('thumbnail'):
                    node['thumbnail'] = f"https://i.ytimg.com/vi/{vid}/maxresdefault.jpg"
                if not node.get('url'):
                    node['url'] = f"https://www.youtube.com/watch?v={vid}"
                # description and clean_description
                if not node.get('description'):
                    node['description'] = data.get('description') or ''
                if not node.get('clean_description'):
                    node['clean_description'] = clean_text_for_storage(data.get('description') or '')
    except Exception:
        pass
    
    # Save updated graphs.json (with card data merged into nodes)
    print(f"\n💾 Saving updated graphs to {INPUT_FILE}...")
    try:
        with open(INPUT_FILE, 'w', encoding='utf-8') as f:
            json.dump(graphs_json, f, indent=2, ensure_ascii=False)
        graphs_saved = True
    except Exception:
        graphs_saved = False
    
    # Summary
    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    print(f"Total attempted: {len(to_process)}")
    print(f"Successful:   {successful} ✓")
    print(f"Failed:       {failed} ✗")
    if graphs_saved:
        print(f"\nGraphs updated: {INPUT_FILE}")
    else:
        print("\nGraphs not updated due to write error")
    print("=" * 60)

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n⚠️  Interrupted by user. Exiting...")
        sys.exit(0)
    except Exception as e:
        print(f"\n❌ Fatal error: {str(e)}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
#!/usr/bin/env python3
# """
# Batch YouTube Card Data Extractor
# Automatically extracts card timing and position data from YouTube videos
# """

# import json
# import time
# import sys
# import os
# import re
# from selenium import webdriver
# from selenium.webdriver.chrome.service import Service
# from selenium.webdriver.chrome.options import Options
# from selenium.webdriver.support.ui import WebDriverWait
# from selenium.webdriver.support import expected_conditions as EC
# from selenium.webdriver.common.by import By

# # JavaScript to extract card data from the page
# EXTRACT_SCRIPT = """
# function extractCardData() {
#     try {
#         let playerResponse = window.ytInitialPlayerResponse;
        
#         if (!playerResponse) {
#             const scripts = document.querySelectorAll('script');
#             for (let script of scripts) {
#                 const content = script.textContent;
#                 if (content.includes('ytInitialPlayerResponse')) {
#                     const match = content.match(/ytInitialPlayerResponse\\s*=\\s*({.+?});/);
#                     if (match) {
#                         playerResponse = JSON.parse(match[1]);
#                         break;
#                     }
#                 }
#             }
#         }
        
#         if (!playerResponse) {
#             return { error: 'No player data found' };
#         }
        
#         const result = {
#             videoId: playerResponse.videoDetails?.videoId,
#             title: playerResponse.videoDetails?.title,
#             lengthSeconds: playerResponse.videoDetails?.lengthSeconds,
#             description: playerResponse.videoDetails?.shortDescription || '',
#             endscreen: []
#         };
        
        
        
#         // Extract endscreen elements
#         if (playerResponse.endscreen?.endscreenRenderer?.elements) {
#             result.endscreen = playerResponse.endscreen.endscreenRenderer.elements.map(element => {
#                 const renderer = element.endscreenElementRenderer;
#                 if (!renderer) return null;
                
#                 return {
#                     style: renderer.style,
#                     startMs: renderer.startMs,
#                     endMs: renderer.endMs,
#                     left: renderer.left,
#                     top: renderer.top,
#                     width: renderer.width,
#                     aspectRatio: renderer.aspectRatio,
#                     title: renderer.title?.simpleText || '',
#                     metadata: renderer.metadata?.simpleText || '',
#                     targetId: renderer.endpoint?.watchEndpoint?.videoId || 
#                              renderer.endpoint?.urlEndpoint?.url || null
#                 };
#             }).filter(e => e !== null);
#         }
        
#         return result;
#     } catch (error) {
#         return { error: error.toString() };
#     }
# }

# return extractCardData();
# """

# def setup_driver(headless=True):
#     """Setup Chrome WebDriver with appropriate options"""
#     chrome_options = Options()
    
#     if headless:
#         chrome_options.add_argument('--headless=new')
    
#     chrome_options.add_argument('--no-sandbox')
#     chrome_options.add_argument('--disable-dev-shm-usage')
#     chrome_options.add_argument('--disable-blink-features=AutomationControlled')
#     # Allow autoplay so we can mute/play programmatically
#     chrome_options.add_argument('--autoplay-policy=no-user-gesture-required')
#     # Mute audio at the browser level so tabs start muted immediately
#     chrome_options.add_argument('--mute-audio')
#     # Use eager page load to speed things up
#     try:
#         chrome_options.page_load_strategy = 'eager'
#     except Exception:
#         pass
    
#     # Force English language
#     chrome_options.add_argument('--lang=en-US')
#     chrome_options.add_experimental_option('prefs', {
#         'intl.accept_languages': 'en-US,en'
#     })
    
#     chrome_options.add_argument('--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36')
    
#     # Ad blocking via preferences
#     chrome_options.add_argument('--disable-popup-blocking')
#     chrome_options.add_experimental_option('prefs', {
#         'intl.accept_languages': 'en-US,en',
#         'profile.default_content_setting_values.notifications': 2,
#         'profile.default_content_settings.popups': 0,
#         # Disable images to reduce bandwidth and speed up loading
#         'profile.managed_default_content_settings.images': 2
#     })
    
#     # Disable logging
#     chrome_options.add_experimental_option('excludeSwitches', ['enable-logging'])
    
#     driver = webdriver.Chrome(options=chrome_options)
    
#     # Set YouTube language cookie
#     driver.get('https://www.youtube.com')
#     driver.add_cookie({
#         'name': 'PREF',
#         'value': 'f1=50000000&hl=en',
#         'domain': '.youtube.com'
#     })
    
#     return driver

# def load_graph_info(json_file):
#     """Load graphs.json and return existing node ids and referenced ids (outgoing/incoming)
#     Returns (set(existing_node_ids), set(referenced_ids))
#     """
#     try:
#         with open(json_file, 'r', encoding='utf-8') as f:
#             data = json.load(f)
#     except FileNotFoundError:
#         print(f"Error: File '{json_file}' not found")
#         return set(), set()
#     except json.JSONDecodeError:
#         print(f"Error: Invalid JSON in '{json_file}'")
#         return set(), set()

#     existing = set()
#     referenced = set()

#     for graph_key, graph_data in data.get('graphs', {}).items():
#         nodes = graph_data.get('nodes', {})
#         for node_id, node_data in nodes.items():
#             existing.add(node_id)

#             # collect outgoing 'to' ids
#             for out in node_data.get('outgoing', []):
#                 to = out.get('to')
#                 if to:
#                     referenced.add(to)

#             # collect incoming 'from' ids
#             for inc in node_data.get('incoming_from', []):
#                 fr = inc.get('from')
#                 if fr:
#                     referenced.add(fr)

#     return existing, referenced

# def load_existing_card_data(json_file):
#     try:
#         with open(json_file, 'r', encoding='utf-8') as f:
#             return json.load(f)
#     except FileNotFoundError:
#         return {}
#     except json.JSONDecodeError:
#         return {}

# def extract_video_data(driver, video_id, delay=3):
#     """Extract card data from a single video"""
#     url = f"https://www.youtube.com/watch?v={video_id}"
    
#     try:
#         print(f"  Loading {video_id}...", end=' ', flush=True)
#         driver.get(url)
        
#         # Handle cookie consent popup (if it appears)
#         try:
#             # Try multiple possible cookie consent button selectors
#             consent_selectors = [
#                 "button[aria-label*='Accept']",
#                 "button[aria-label*='accept']",
#                 "button.yt-spec-button-shape-next--filled",
#                 "ytd-button-renderer button"
#             ]
#             for selector in consent_selectors:
#                 try:
#                     consent_button = WebDriverWait(driver, 2).until(
#                         EC.element_to_be_clickable((By.CSS_SELECTOR, selector))
#                     )
#                     aria_label = consent_button.get_attribute('aria-label')
#                     if 'accept' in consent_button.text.lower() or (aria_label and 'accept' in aria_label.lower()):
#                         consent_button.click()
#                         time.sleep(1)
#                         break
#                 except:
#                     continue
#         except:
#             pass  # No consent popup or already accepted
        
#         # Wait for page to load the player if not present
#         try:
#             WebDriverWait(driver, 10).until(
#                 EC.presence_of_element_located((By.ID, "movie_player"))
#             )
#         except Exception:
#             pass
        
#         # Try to skip ads if present
#         try:
#             skip_button_selectors = [
#                 ".ytp-ad-skip-button",
#                 ".ytp-skip-ad-button",
#                 "button.ytp-ad-skip-button-modern"
#             ]
#             for selector in skip_button_selectors:
#                 try:
#                     skip_button = WebDriverWait(driver, 2).until(
#                         EC.element_to_be_clickable((By.CSS_SELECTOR, selector))
#                     )
#                     skip_button.click()
#                     time.sleep(0.5)
#                     break
#                 except:
#                     continue
#         except:
#             pass  # No ads or already skipped
        
#         # Additional wait for JavaScript to fully load
#         time.sleep(delay)
        
#         # Execute extraction script
#         data = driver.execute_script(EXTRACT_SCRIPT)
        
#         if 'error' in data:
#             print(f"❌ Error: {data['error']}")
#             return None
        
#         # Count items found
#         endscreen_count = len(data.get('endscreen', []))
#         print(f"✓ Found {endscreen_count} endscreen elements")

        
#         return data
        
#     except Exception as e:
#         print(f"❌ Failed: {str(e)}")
#         return None

# def load_existing_videos(json_file):
#     """Load video IDs from existing graphs.json"""
#     try:
#         with open(json_file, 'r', encoding='utf-8') as f:
#             data = json.load(f)
        
#         video_ids = []
        
#         # Extract all unique video IDs from the graph
#         for graph_key, graph_data in data.get('graphs', {}).items():
#             for node_id, node_data in graph_data.get('nodes', {}).items():
#                 if node_id not in video_ids:
#                     video_ids.append(node_id)
        
#         return video_ids
    
#     except FileNotFoundError:
#         print(f"Error: File '{json_file}' not found")
#         return []
#     except json.JSONDecodeError:
#         print(f"Error: Invalid JSON in '{json_file}'")
#         return []


# def clean_text_for_storage(text: str) -> str:
#     """Match backend.clean_description: remove choice links, short prompts, URLs, and skip empty lines.

#     Keeps meaningful newlines between retained lines.
#     """
#     if not text:
#         return ''
#     # normalize line endings
#     s = text.replace('\r\n', '\n').replace('\r', '\n')
#     # remove simple HTML tags
#     s = re.sub(r'<[^>]+>', '', s)
#     lines = s.split('\n')
#     cleaned_lines = []
#     for line in lines:
#         line_stripped = line.strip()
#         if not line_stripped:
#             continue
#         # Skip lines with choice markers
#         if '►' in line_stripped:
#             continue
#         # Skip short questions (prompts)
#         if line_stripped.endswith('?') and len(line_stripped) < 20:
#             continue
#         # Skip URLs-only lines
#         if line_stripped.startswith('http://') or line_stripped.startswith('https://'):
#             continue
#         cleaned_lines.append(line_stripped)

#     return '\n'.join(cleaned_lines).strip()

# def main():
#     # Configuration
#     # Prefer backend data file when available so updates go to the canonical store
#     default_backend = os.path.normpath(os.path.join(os.path.dirname(__file__), '..', 'backend', 'data', 'graphs.json'))
#     INPUT_FILE = default_backend if os.path.exists(default_backend) else 'graphs.json'
#     HEADLESS = False  # Set to False to see the browser
#     DELAY_BETWEEN_VIDEOS = 1  # Seconds to wait for each page to load
#     MAX_VIDEOS = 0  # 0 = process all missing; >0 = limit to that many videos
    
#     print("=" * 60)
#     print("YouTube Card Data Batch Extractor")
#     print("=" * 60)
    
#     # Load graph info and existing extracted card data
#     print(f"\n📂 Loading graph info from {INPUT_FILE}...")
#     existing_nodes, referenced_ids = load_graph_info(INPUT_FILE)

#     # Load full graphs JSON so we can check which nodes already have card data
#     try:
#         with open(INPUT_FILE, 'r', encoding='utf-8') as f:
#             graphs_json = json.load(f)
#     except Exception:
#         graphs_json = {"graphs": {}}

#     # Videos that exist as nodes but missing extracted card data
#     nodes_missing_cards = []
#     for gkey, gdata in graphs_json.get('graphs', {}).items():
#         for node_id, node_data in gdata.get('nodes', {}).items():
#             if node_id in existing_nodes:
#                 if not node_data.get('card_data'):
#                     nodes_missing_cards.append(node_id)

#     # Videos referenced in outgoing/incoming but missing as full nodes
#     missing_nodes = list(referenced_ids - existing_nodes)

#     # Prepare list: prioritize completely missing nodes, then nodes missing cards
#     to_process = missing_nodes + [v for v in nodes_missing_cards if v not in missing_nodes]

#     if not to_process:
#         print("❌ No missing videos or missing card data found. Exiting.")
#         return

#     if MAX_VIDEOS > 0:
#         to_process = to_process[:MAX_VIDEOS]

#     print(f"✓ Found {len(to_process)} videos to process (missing: {len(missing_nodes)}, missing_cards: {len(nodes_missing_cards)})")
    
#     # Setup browser
#     print("\n🌐 Starting Chrome browser...")
#     driver = setup_driver(headless=HEADLESS)
    
#     # Extract data from all videos
#     results = {}
#     successful = 0
#     failed = 0
    
#     print(f"\n📹 Processing {len(to_process)} videos...\n")
    
#     # Attempt to import backend crawler to run crawl logic for new nodes
#     crawler = None
#     crawled_targets = set()
#     try:
#         backend_dir = os.path.normpath(os.path.join(os.path.dirname(__file__), '..', 'backend'))
#         if backend_dir not in sys.path:
#             sys.path.insert(0, backend_dir)
#         import crawler as backend_crawler
#         crawler = backend_crawler
#     except Exception:
#         crawler = None

#     # container graph key to add new nodes into (use first graph available)
#     container_graph_key = next(iter(graphs_json.get('graphs', {})), None)

#     for i, video_id in enumerate(to_process, 1):
#         print(f"[{i}/{len(to_process)}]", end=' ')

#         data = extract_video_data(driver, video_id, delay=DELAY_BETWEEN_VIDEOS)
        
#         if data:
#             results[video_id] = data
#             successful += 1
#             # Update graphs.json structure: add node if missing, add outgoing/incoming edges
#             try:
#                 elements = data.get('endscreen', [])
#                 # ensure container exists
#                 if container_graph_key is None:
#                     container_graph_key = video_id
#                     graphs_json.setdefault('graphs', {}).setdefault(container_graph_key, {'title': '', 'nodes': {}})

#                 nodes = graphs_json['graphs'][container_graph_key].setdefault('nodes', {})

#                 # add current node if missing; overwrite only when suspiciously empty
#                 node = nodes.setdefault(video_id, {})
#                 # fill title if empty
#                 if not node.get('title'):
#                     node['title'] = data.get('title') or ''
#                 node.setdefault('thumbnail', f"https://i.ytimg.com/vi/{video_id}/maxresdefault.jpg")
#                 node.setdefault('url', f"https://www.youtube.com/watch?v={video_id}")
#                 # fill description if empty using extracted full description
#                 if not node.get('description'):
#                     node['description'] = data.get('description') or ''
#                 node.setdefault('outgoing', [])
#                 node.setdefault('incoming_from', [])
#                 # set clean_description if missing
#                 if not node.get('clean_description'):
#                     desc = data.get('description') or ''
#                     node['clean_description'] = clean_text_for_storage(desc) if desc else ''
#                 # attach card data
#                 node.setdefault('card_data', {})

#                 # process outgoing targets
#                 for el in elements:
#                     target = el.get('targetId')
#                     label = el.get('title') or el.get('metadata') or ''
#                     if not target:
#                         continue

#                     # add outgoing entry on current node (avoid dup)
#                     if not any(o.get('to') == target for o in node.get('outgoing', [])):
#                         node['outgoing'].append({'to': target, 'label': label})

#                     # ensure target node exists; if not, create minimal
#                     target_node = nodes.setdefault(target, {})
#                     target_node.setdefault('title', '')
#                     target_node.setdefault('thumbnail', f"https://i.ytimg.com/vi/{target}/maxresdefault.jpg")
#                     target_node.setdefault('url', f"https://www.youtube.com/watch?v={target}")
#                     target_node.setdefault('description', '')
#                     target_node.setdefault('outgoing', [])
#                     target_node.setdefault('incoming_from', [])

#                     # If the endscreen provided a title, use it when the target's title is empty
#                     try:
#                         el_title = el.get('title')
#                         if el_title and not target_node.get('title'):
#                             target_node['title'] = el_title
#                     except Exception:
#                         pass

#                     # Add element metadata onto the target node itself (only once)
#                     try:
#                         meta = el.get('metadata')
#                         if meta and not target_node.get('card_metadata'):
#                             target_node['card_metadata'] = meta
#                     except Exception:
#                         pass

#                     # If this target was one of the missing nodes, invoke crawler to populate it (once)
#                     try:
#                         if crawler and target in missing_nodes and target not in crawled_targets:
#                             print(f"\nInvoking crawler.run_crawl for {target}...", end=' ')
#                             try:
#                                 crawler.run_crawl(target, max_nodes=10)
#                                 crawled_targets.add(target)
#                                 print("done")
#                             except Exception as e:
#                                 print(f"failed: {e}")
#                     except Exception:
#                         pass

#                     # add incoming entry to target (avoid dup)
#                     if not any(inc.get('from') == video_id for inc in target_node.get('incoming_from', [])):
#                         target_node['incoming_from'].append({'from': video_id, 'label': label})
#                 # attach cleaned card data to current node only if missing (avoid duplicate overwrite)
#                 if data and not node.get('card_data'):
#                     try:
#                         cleaned = {}
#                         cleaned['endscreen'] = []
#                         for el in data.get('endscreen', []):
#                             # keep only the essential layout/timing fields
#                             keep = ['aspectRatio', 'endMs', 'left', 'startMs', 'targetId', 'top', 'width']
#                             new_el = {k: el.get(k) for k in keep if el.get(k) is not None}
#                             if new_el:
#                                 cleaned['endscreen'].append(new_el)
#                         if data.get('lengthSeconds') is not None:
#                             cleaned['lengthSeconds'] = data.get('lengthSeconds')
#                         node['card_data'] = cleaned
#                     except Exception:
#                         node['card_data'] = {}
#             except Exception as e:
#                 print(f"\nWarning updating graphs.json: {e}")
#         else:
#             failed += 1
        
#         # Small delay between requests to be polite
#         time.sleep(0.5)
    
#     # Close browser
#     driver.quit()
    
#     # Backfill any missing metadata on nodes for videos we just scraped
#     try:
#         for vid, data in results.items():
#             for gkey, gdata in graphs_json.get('graphs', {}).items():
#                 node = gdata.get('nodes', {}).get(vid)
#                 if not node:
#                     continue
#                 # title
#                 if not node.get('title'):
#                     node['title'] = data.get('title') or ''
#                 # thumbnail/url
#                 if not node.get('thumbnail'):
#                     node['thumbnail'] = f"https://i.ytimg.com/vi/{vid}/maxresdefault.jpg"
#                 if not node.get('url'):
#                     node['url'] = f"https://www.youtube.com/watch?v={vid}"
#                 # description and clean_description
#                 if not node.get('description'):
#                     node['description'] = data.get('description') or ''
#                 if not node.get('clean_description'):
#                     node['clean_description'] = clean_text_for_storage(data.get('description') or '')
#     except Exception:
#         pass
    
#     # Save updated graphs.json (with card data merged into nodes)
#     print(f"\n💾 Saving updated graphs to {INPUT_FILE}...")
#     try:
#         with open(INPUT_FILE, 'w', encoding='utf-8') as f:
#             json.dump(graphs_json, f, indent=2, ensure_ascii=False)
#         graphs_saved = True
#     except Exception:
#         graphs_saved = False
    
#     # Summary
#     print("\n" + "=" * 60)
#     print("SUMMARY")
#     print("=" * 60)
#     print(f"Total attempted: {len(to_process)}")
#     print(f"Successful:   {successful} ✓")
#     print(f"Failed:       {failed} ✗")
#     if graphs_saved:
#         print(f"\nGraphs updated: {INPUT_FILE}")
#     else:
#         print("\nGraphs not updated due to write error")
#     print("=" * 60)

# if __name__ == "__main__":
#     try:
#         main()
#     except KeyboardInterrupt:
#         print("\n\n⚠️  Interrupted by user. Exiting...")
#         sys.exit(0)
#     except Exception as e:
#         print(f"\n❌ Fatal error: {str(e)}")
#         import traceback
#         traceback.print_exc()
#         sys.exit(1)