(function(){
  const width = 3000, height = 2500;
  const svg = d3.select('#graph').append('svg').attr('width', width).attr('height', height);
  const container = svg.append('g'); // Remove the hardcoded translate

  // zoom/pan
  const zoom = d3.zoom().scaleExtent([0.1, 4]).on('zoom', (event) => {
    container.attr('transform', event.transform);
  });
  svg.call(zoom);

  // Set initial zoom to account for the offset we used to have
  const initialTransform = d3.zoomIdentity.translate(100, 50);
  svg.call(zoom.transform, initialTransform);

  let currentGraphKey = null;
  let allGraphData = null;

  // Load graph list and populate dropdown
  fetch('/graph').then(r=>r.json()).then(data => {
    allGraphData = data;
    const graphSelect = document.getElementById('graphSelect');
    const keys = Object.keys(data.graphs || {'default': data});
    
    keys.forEach((key, idx) => {
      const option = document.createElement('option');
      option.value = key;
      option.textContent = data.graphs ? data.graphs[key].title || key : 'Main Graph';
      graphSelect.appendChild(option);
    });
    
    graphSelect.addEventListener('change', (e) => {
      currentGraphKey = e.target.value;
      localStorage.setItem('selectedGraph', currentGraphKey);
      renderGraph(currentGraphKey);
    });
    
    // Restore previously selected graph from localStorage, or use first graph
    const savedGraph = localStorage.getItem('selectedGraph');
    currentGraphKey = (savedGraph && keys.includes(savedGraph)) ? savedGraph : keys[0];
    graphSelect.value = currentGraphKey;
    renderGraph(currentGraphKey);
  });

  // Add trailer button handler
  document.getElementById('addTrailerBtn').addEventListener('click', async () => {
    const trailerUrl = prompt('Enter trailer YouTube URL:');
    if (!trailerUrl) return;
    
    try {
      const response = await fetch('/add_trailer', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({
          graph_id: currentGraphKey,
          trailer_url: trailerUrl
        })
      });
      
      const result = await response.json();
      if (response.ok) {
        alert('Trailer added successfully! Reloading graph...');
        location.reload();
      } else {
        alert('Error: ' + (result.error || 'Unknown error'));
      }
    } catch (e) {
      alert('Error adding trailer: ' + e.message);
    }
  });

  // Add bonus button handler
  document.getElementById('addBonusBtn').addEventListener('click', async () => {
    const bonusUrls = prompt('Enter bonus content URLs (comma-separated):');
    if (!bonusUrls) return;
    
    try {
      const response = await fetch('/add_bonus', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({
          graph_id: currentGraphKey,
          bonus_urls: bonusUrls
        })
      });
      
      const result = await response.json();
      if (response.ok) {
        alert('Bonus content added successfully! Reloading graph...');
        location.reload();
      } else {
        alert('Error: ' + (result.error || 'Unknown error'));
      }
    } catch (e) {
      alert('Error adding bonus content: ' + e.message);
    }
  });

  // Toggle bonus button handler
  document.getElementById('toggleBonusBtn').addEventListener('click', async () => {
    if (!confirm('Hide the "Add Bonus Content" button? You can re-enable it by editing the JSON file.')) return;
    
    try {
      const response = await fetch('/toggle_bonus_button', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({
          graph_id: currentGraphKey,
          hide: true
        })
      });
      
      const result = await response.json();
      if (response.ok) {
        alert('Bonus button hidden. Edit JSON to re-enable.');
        location.reload();
      } else {
        alert('Error: ' + (result.error || 'Unknown error'));
      }
    } catch (e) {
      alert('Error toggling bonus button: ' + e.message);
    }
  });

  function renderGraph(graphKey) {
    // Clear previous render
    container.selectAll('*').remove();
    
    // Remove clear lock button if it exists
    d3.select('#clear-lock-btn').remove();
    
    // Recreate marker definition
    const defs = container.append('defs');
    defs.append('marker')
      .attr('id','arrow')
      .attr('viewBox','0 0 10 10')
      .attr('refX',9)
      .attr('refY',5)
      .attr('markerWidth',8)
      .attr('markerHeight',8)
      .attr('orient','auto-start-reverse')
      .append('path')
      .attr('d','M 0 0 L 10 5 L 0 10 z')
      .attr('fill','#666');
    
    const graph = allGraphData.graphs ? allGraphData.graphs[graphKey] : allGraphData;
    
    // Show/hide add trailer button: show only if trailer is null/undefined, hide if set to any value (including 'none')
    const addTrailerBtn = document.getElementById('addTrailerBtn');
    if (graph.trailer_video_id) {
      addTrailerBtn.style.display = 'none';
    } else {
      addTrailerBtn.style.display = 'block';
    }
    
    // Show/hide add bonus button and toggle based on hide_bonus_button flag
    const addBonusBtn = document.getElementById('addBonusBtn');
    const toggleBonusBtn = document.getElementById('toggleBonusBtn');
    
    if (graph.hide_bonus_button) {
      addBonusBtn.style.display = 'none';
      toggleBonusBtn.style.display = 'none';
    } else {
      addBonusBtn.style.display = 'block';
      toggleBonusBtn.style.display = 'block';
    }
    
    render(graph);
  }

  function truncate(s, n=40){ if(!s) return ''; return s.length>n ? s.slice(0,n-1)+'…' : s; }
  function wrapText(text, maxWidth) {
    const words = text.split(' ');
    const lines = [];
    let currentLine = '';
    let hasMore = false;
    
    words.forEach((word, idx) => {
      // If we already have 2 lines, mark that there's more and stop
      if(lines.length >= 2) {
        hasMore = true;
        return;
      }
      
      // If the word itself is longer than maxWidth, truncate it
      if(word.length > maxWidth) {
        // If current line has content, push it first
        if(currentLine) {
          lines.push(currentLine);
          currentLine = '';
        }
        // If we still have room for lines, add truncated word
        if(lines.length < 2) {
          lines.push(word.slice(0, maxWidth - 1) + '…');
          hasMore = true;
        }
        return;
      }
      
      const testLine = currentLine ? currentLine + ' ' + word : word;
      if (testLine.length > maxWidth) {
        if(currentLine) lines.push(currentLine);
        currentLine = word;
      } else {
        currentLine = testLine;
      }
    });
    
    // Add remaining line if we have space
    if(currentLine && lines.length < 2) {
      lines.push(currentLine);
    } else if(currentLine) {
      hasMore = true;
    }
    
    // Add ellipsis to last line if there's more content
    if(hasMore && lines.length > 0) {
      lines[lines.length - 1] = lines[lines.length - 1] + '…';
    }
    
    return lines;
  }

  function render(graph){
    const nodesData = graph.nodes;
    const part2VideoId = graph.part2_video_id;
    const stopVideoIds = new Set(graph.stop_video_ids || []);
    const trailerVideoId = (graph.trailer_video_id && graph.trailer_video_id !== 'none') ? graph.trailer_video_id : null;
    const bonusVideoIds = new Set(graph.bonus_video_ids || []);
    
    // State for locked highlight
    let isLocked = false;
    let lockedNodeId = null;
    
    // Convert to array
    const nodes = Object.keys(nodesData).map(id => Object.assign({id}, nodesData[id]));
    
    // Separate bonus nodes from regular nodes - bonus nodes are standalone
    const regularNodes = nodes.filter(n => !bonusVideoIds.has(n.id));
    
    // Find roots (nodes with no incoming_from), excluding Part 2, trailer, and bonus
    const rootCandidates = regularNodes.filter(n => 
      (!n.incoming_from || n.incoming_from.length === 0) && n.id !== part2VideoId && n.id !== trailerVideoId
    );
    
    // Main root is the first non-Part 2 root
    const root = rootCandidates[0] || regularNodes[0];
    
    console.log('Root node:', root.id, root.title);
    console.log('Root candidates:', rootCandidates.map(n => ({id: n.id, title: n.title})));
    console.log('Part 2 video ID:', part2VideoId);
    
    // Identify Part 2 nodes (separate tree)
    const part2Root = part2VideoId ? regularNodes.find(n => n.id === part2VideoId) : null;
    console.log('Part 2 root:', part2Root ? {id: part2Root.id, title: part2Root.title} : 'None');
    
    // Update stats display
    document.getElementById('nodeCount').textContent = nodes.length;
    const totalConnections = nodes.reduce((sum, n) => sum + (n.outgoing ? n.outgoing.length : 0), 0);
    document.getElementById('connectionCount').textContent = totalConnections;
    
    // Part 2 node identification will happen after hierarchy is built
    
    // Build links from outgoing
    const links = [];
    nodes.forEach(node => {
      if(node.outgoing) {
        node.outgoing.forEach(out => {
          links.push({source: node.id, target: out.to, label: out.label});
        });
      }
    });

    // Create hierarchy - Build tree from root using BFS to get shortest paths
    // This ensures each node appears at the correct depth (shortest path from root)
    const nodeDepths = new Map();
    const nodeParents = new Map();
    
    // If trailer exists, handle it separately
    const trailerNode = trailerVideoId ? nodes.find(n => n.id === trailerVideoId) : null;
    if (trailerNode) {
      nodeDepths.set(trailerVideoId, -1); // Trailer at depth -1 (above root)
      nodeParents.set(trailerVideoId, null);
    }
    
    // BFS to find shortest path depth for each node
    const queue = [{id: root.id, depth: 0, parent: null}];
    nodeDepths.set(root.id, 0);
    
    while(queue.length > 0) {
      const {id, depth, parent} = queue.shift();
      const node = regularNodes.find(n => n.id === id);
      if(!node) continue;
      
      if(node.outgoing) {
        node.outgoing.forEach(out => {
          // Only visit if not visited OR if this path is shorter
          if(!nodeDepths.has(out.to)) {
            nodeDepths.set(out.to, depth + 1);
            nodeParents.set(out.to, id);
            queue.push({id: out.to, depth: depth + 1, parent: id});
          }
        });
      }
    }
    
    // Build tree structure based on shortest paths
    const buildTree = (nodeId) => {
      const node = regularNodes.find(n => n.id === nodeId);
      if(!node) return null;
      
      // Find all children (nodes where this node is the parent in shortest path)
      const children = [];
      nodeParents.forEach((parentId, childId) => {
        if(parentId === nodeId) {
          const childTree = buildTree(childId);
          if(childTree) children.push(childTree);
        }
      });
      
      return {...node, children};
    };
    
    // Build complete tree from root (includes Part 2 as a child node)
    const completeTree = buildTree(root.id);
    console.log('Complete tree structure:', completeTree);
    const hierarchyRoot = d3.hierarchy(completeTree);
    console.log('Hierarchy root descendants:', hierarchyRoot.descendants().map(n => ({id: n.data.id, title: n.data.title, depth: n.depth})));
    
    // Re-identify Part 2 nodes based on hierarchy (not graph traversal)
    // Find Part 2 node in hierarchy
    const part2HierarchyNode = hierarchyRoot.descendants().find(n => n.data.id === part2VideoId);
    const part2NodeIds = new Set();
    if(part2HierarchyNode) {
      // Mark Part 2 and all its descendants in the hierarchy
      part2HierarchyNode.descendants().forEach(n => {
        part2NodeIds.add(n.data.id);
      });
      console.log('Part 2 nodes in hierarchy:', Array.from(part2NodeIds));
    }

    // Layered vertical layout
    const layerHeight = 220;
    const nodeSpacing = 200;
    const part2Offset = 100; // Small gap before Part 2
    
    // First, calculate natural depths
    const layers = {};
    hierarchyRoot.descendants().forEach(node => {
      if(!layers[node.depth]) layers[node.depth] = [];
      layers[node.depth].push(node);
    });
    
    // Add trailer node to layers manually if it exists
    if (trailerNode) {
      // Create a hierarchy node-like object for the trailer
      const trailerHierarchyNode = {
        data: trailerNode,
        depth: -1,
        y: -150,
        x: width / 2
      };
      if (!layers[-1]) layers[-1] = [];
      layers[-1].push(trailerHierarchyNode);
    }
    
    // Prepare bonus nodes separately - DON'T add to layers to avoid interfering with normal layout
    // Position them horizontally to the right of each other
    const bonusNodes = [];
    if (bonusVideoIds.size > 0) {
      // First bonus node position (original position that worked)
      const bonusStartX = width / 2 + 280;
      const bonusStartY = 50;
      const bonusHorizontalSpacing = 220; // Horizontal spacing between bonus nodes
      
      let index = 0;
      bonusVideoIds.forEach((bonusId) => {
        const bonusNode = nodes.find(n => n.id === bonusId);
        if (bonusNode) {
          const enhancedNode = {...bonusNode};
          const originalDesc = bonusNode.clean_description || 'No Description';
          enhancedNode.clean_description = `${originalDesc}`;
          
          // Position bonus nodes horizontally to the right of the first one
          bonusNodes.push({
            data: enhancedNode,
            depth: 0,
            y: bonusStartY, // Same Y for all (horizontal line)
            x: bonusStartX + (index * bonusHorizontalSpacing) // Space them horizontally
          });
          index++;
        }
      });
    }
    
    // Find all nodes that connect to Part 2
    const nodesConnectingToPart2 = new Set();
    if(part2VideoId) {
      regularNodes.forEach(node => {
        if(node.outgoing) {
          node.outgoing.forEach(out => {
            if(out.to === part2VideoId) {
              nodesConnectingToPart2.add(node.id);
            }
          });
        }
      });
    }
    
    // Find the maximum depth of nodes connecting to Part 2 (excluding Part 2 nodes themselves)
    let maxDepthBeforePart2 = 0;
    if(part2VideoId && nodesConnectingToPart2.size > 0) {
      hierarchyRoot.descendants().forEach(node => {
        // Only count Part 1 nodes (not Part 2 nodes) that connect to Part 2
        if(nodesConnectingToPart2.has(node.data.id) && !part2NodeIds.has(node.data.id)) {
          console.log('Node connecting to Part 2:', node.data.id, node.data.title, 'at depth:', node.depth);
          maxDepthBeforePart2 = Math.max(maxDepthBeforePart2, node.depth);
        }
      });
    }
    
    // Position Part 2 start one level below the deepest node connecting to it
    const part2StartDepth = maxDepthBeforePart2 + 1;
    
    console.log('Nodes connecting to Part 2:', Array.from(nodesConnectingToPart2));
    console.log('Max depth before Part 2:', maxDepthBeforePart2);
    console.log('Part 2 start will be at depth:', part2StartDepth);
    
    // Position all nodes
    Object.keys(layers).forEach(depth => {
      const depthNodes = layers[depth];
      depthNodes.forEach((node, i) => {
        const isPart2Node = part2NodeIds.has(node.data.id);
        
        if(node.data.id === trailerVideoId) {
          // Trailer: position above root, centered
          node.y = -150; // Above the root
          node.x = width / 2;
        } else if(node.data.id === part2VideoId) {
          // Part 2 start: position at calculated depth, centered with starting node
          node.y = part2StartDepth * layerHeight + part2Offset + 100;
          node.x = width / 2; // Center with starting node
        } else if(isPart2Node) {
          // Other Part 2 nodes: relative to Part 2 start
          const part2Node = hierarchyRoot.descendants().find(n => n.data.id === part2VideoId);
          const relativeDepth = node.depth - part2Node.depth;
          node.y = part2StartDepth * layerHeight + part2Offset + 100 + relativeDepth * layerHeight;
          node.x = (i - depthNodes.length / 2) * nodeSpacing + width / 2;
        } else {
          // Part 1 nodes: normal positioning
          node.y = node.depth * layerHeight + 100;
          node.x = (i - depthNodes.length / 2) * nodeSpacing + width / 2;
        }
      });
    });

    // Identify node types
    const hasIncoming = new Set(links.map(l=>l.target));
    const hasOutgoing = new Set(links.map(l=>l.source));
    const startNodes = regularNodes.filter(n => !hasIncoming.has(n.id));
    const endNodes = regularNodes.filter(n => !hasOutgoing.has(n.id));
    
    console.log('Start nodes:', startNodes.map(n => n.id));
    console.log('End nodes:', endNodes.map(n => n.id));
    console.log('Has incoming size:', hasIncoming.size);
    console.log('Has outgoing size:', hasOutgoing.size);
    
    // Part 2 connection nodes are nodes that link to Part 2 root
    const part2ConnectionNodes = new Set();
    if(part2VideoId) {
      regularNodes.forEach(node => {
        if(node.outgoing) {
          node.outgoing.forEach(out => {
            if(out.to === part2VideoId) {
              part2ConnectionNodes.add(node.id);
            }
          });
        }
      });
    }
    
    // Nodes that connect directly to start nodes or Part 2 node (loop-back endings)
    const loopBackNodes = new Set();
    regularNodes.forEach(node => {
      if(node.outgoing) {
        node.outgoing.forEach(out => {
          // Check if this node connects back to the root or Part 2 root
          if(out.to === root.id || out.to === part2VideoId) {
            if(node.id !== root.id && node.id !== part2VideoId) {
              loopBackNodes.add(node.id);
            }
          }
        });
      }
    });
    
    const nodeRadius = 85;

    // Create links
    const link = container.append('g').attr('class','links')
      .selectAll('path')
      .data(links)
      .enter().append('path')
      .attr('stroke','#666')
      .attr('stroke-width', 2)
      .attr('fill','none')
      .attr('class', 'link-path')
      .attr('marker-end', 'url(#arrow)')
      .attr('d', d => {
        // Create combined node list including trailer
        const allNodesForLookup = hierarchyRoot.descendants();
        if (trailerNode && layers[-1] && layers[-1].length > 0) {
          allNodesForLookup.push(layers[-1][0]);
        }
        
        const sourceNode = allNodesForLookup.find(n => n.data.id === d.source);
        const targetNode = allNodesForLookup.find(n => n.data.id === d.target);
        if(!sourceNode || !targetNode) return '';
        
        const sx = sourceNode.x;
        const sy = sourceNode.y + nodeRadius;
        const tx = targetNode.x;
        const ty = targetNode.y - nodeRadius - 5; // Stop 5px before node border for marker
        
        return `M${sx},${sy} C${sx},${sy + 60} ${tx},${ty - 60} ${tx},${ty}`;
      });

    const node = container.append('g').attr('class','nodes')
      .selectAll('g')
      .data(() => {
        const allNodes = hierarchyRoot.descendants();
        // Add trailer node if it exists
        if (trailerNode && layers[-1] && layers[-1].length > 0) {
          allNodes.push(layers[-1][0]);
        }
        // Add bonus nodes if they exist
        if (bonusNodes.length > 0) {
          allNodes.push(...bonusNodes);
        }
        return allNodes;
      })
      .enter().append('g')
      .attr('transform', d => `translate(${d.x},${d.y})`)
      .attr('class', 'node-group')
      .style('cursor','pointer');
    
    // Debug: log first node data
    console.log('First node data:', hierarchyRoot.descendants()[0]);
    console.log('Node count:', hierarchyRoot.descendants().length);
    console.log('Max depth before Part 2:', maxDepthBeforePart2);
    console.log('Part 2 start depth:', part2StartDepth);
    
    // Add double-click to open URL (since single click now locks)
    node.on('dblclick', (event, d) => {
      event.stopPropagation();
      window.open(d.data.url,'_blank');
    });

    // Clear lock button
    const clearButton = d3.select('body').append('button')
      .attr('id', 'clear-lock-btn')
      .style('position', 'fixed')
      .style('bottom', '20px')
      .style('right', '20px')
      .style('padding', '12px 24px')
      .style('background', '#f44336')
      .style('color', '#fff')
      .style('border', 'none')
      .style('border-radius', '8px')
      .style('font-size', '14px')
      .style('font-weight', 'bold')
      .style('cursor', 'pointer')
      .style('z-index', '1000')
      .style('display', 'none')
      .style('box-shadow', '0 2px 8px rgba(0,0,0,0.3)')
      .text('Clear Lock')
      .on('click', function() {
        isLocked = false;
        lockedNodeId = null;
        d3.select(this).style('display', 'none');
        // Reset all styles
        node.style('opacity', 1);
        link.style('opacity', 1);
        container.selectAll('.arrow-head').style('opacity', 1);
        node.selectAll('circle').attr('stroke','#333').attr('stroke-width', 3);
        link.attr('stroke','#666').attr('stroke-width', 2);
        container.selectAll('.arrow-head').attr('fill','#666');
      });

    node.append('circle').attr('r', nodeRadius).attr('fill', d => {
      // Bonus nodes - gold/amber color
      if(bonusVideoIds.has(d.data.id)) return '#FFA000'; // Amber/Gold - bonus content
      // Trailer node - light green
      if(d.data.id === trailerVideoId) return '#81C784'; // Light green - trailer
      // Main root node should always be green
      if(d.data.id === root.id) return '#4CAF50'; // Green - Part 1 start (main root)
      if(d.data.id === part2VideoId) return '#4CAF50'; // Green - Part 2 start
      if(stopVideoIds.has(d.data.id)) return '#9C27B0'; // Purple - stop node (crawled but not continued)
      if(part2ConnectionNodes.has(d.data.id)) return '#FF9800'; // Orange - part 2 connection
      if(loopBackNodes.has(d.data.id)) return '#E91E63'; // Pink - loop back to start
      if(endNodes.find(e=>e.id===d.data.id)) return '#f44336'; // Red - end
      return '#2196F3'; // Blue - regular
    }).attr('stroke','#333').attr('stroke-width', 3).attr('fill-opacity', 0.9).attr('class', 'node-circle');
    
    // Add title
    node.each(function(d) {
      const g = d3.select(this);
      const titleLines = wrapText(d.data.title, 18);
      titleLines.forEach((line, i) => {
        g.append('text')
          .attr('y', -50 + i*11)
          .attr('text-anchor','middle')
          .attr('font-size',10)
          .attr('font-weight','bold')
          .attr('fill','#fff')
          .text(line);
      });
    });
    
    // Add image (16:9 aspect ratio)
    const imgWidth = 80;
    const imgHeight = 45; // 16:9 ratio
    node.append('image').attr('href', d=>d.data.thumbnail).attr('x', -imgWidth/2).attr('y', -25).attr('width', imgWidth).attr('height', imgHeight).attr('clip-path', 'inset(0 round 6px)').attr('preserveAspectRatio', 'xMidYMid slice');
    
    // Add description
    node.each(function(d) {
      const desc = d.data.clean_description || '';
      if(desc) {
        const lines = wrapText(desc, 20);
        const g = d3.select(this);
        lines.forEach((line, i) => {
          g.append('text').attr('y', 55 + i*10).attr('text-anchor','middle').attr('font-size',8).attr('fill','#fff').text(line);
        });
      }
    });
    
    node.append('title').text(d=>`${d.data.title}\n${d.data.clean_description || ''}`);
    
    // node.append('title').text(d=>`${d.data.title}\n${d.data.clean_description || ''}`);



    // Spotlight + hover with ALL incoming paths
    node.on('mouseover', function(event, d) {
      // Don't highlight on hover if locked
      if(isLocked) return;
      
      const nodeId = d.data.id;
      // console.log('Hovering node:', nodeId, 'incoming_from:', d.data.incoming_from);
      const outgoingIds = d.data.outgoing ? d.data.outgoing.map(o => o.to) : [];
      
      // Get direct incoming nodes (immediate parents)
      const directIncomingIds = new Set();
      if(d.data.incoming_from) {
        d.data.incoming_from.forEach(incoming => {
          directIncomingIds.add(incoming.from);
        });
      }

      // Get ALL incoming nodes recursively (all possible ways to reach this node)
      const allIncomingIds = new Set();
      const visited = new Set();

      function findAllIncoming(currentNodeId, depth = 0) {
        // Limit recursion depth to prevent infinite loops
        if(depth > 10 || visited.has(currentNodeId)) return;
        visited.add(currentNodeId);
        
        // Find the node data for currentNodeId
        let currentNode = null;
        node.each(function(nodeData) {
          if(nodeData.data.id === currentNodeId) {
            currentNode = nodeData.data;
          }
        });
        
        if(currentNode && currentNode.incoming_from) {
          currentNode.incoming_from.forEach(incoming => {
            // Don't add or recurse through loop-back nodes (pink nodes)
            if(!loopBackNodes.has(incoming.from)) {
              allIncomingIds.add(incoming.from);
              findAllIncoming(incoming.from, depth + 1);
            }
          });
        }
      }

      // Start recursion from ALL direct incoming nodes, not just the current node
      directIncomingIds.forEach(incomingId => {
        findAllIncoming(incomingId);
      });
      
      // findAllIncoming(nodeId);
      
      // Dim all nodes (slightly transparent)
      node.each(function(nodeData) {
        const isOutgoing = outgoingIds.includes(nodeData.data.id);
        const isDirectIncoming = directIncomingIds.has(nodeData.data.id);
        const isIndirectIncoming = allIncomingIds.has(nodeData.data.id) && !isDirectIncoming;
        const isCurrent = nodeData.data.id === nodeId;
        
        if(isCurrent) {
          // Current node - full opacity
          d3.select(this).style('opacity', 1);
        } else if(isOutgoing) {
          // Outgoing - purple, full opacity
          d3.select(this).style('opacity', 1);
          d3.select(this).select('circle')
            .attr('stroke', '#9C27B0')
            .attr('stroke-width', 6);
        } else if(isDirectIncoming) {
          // Direct incoming - gold, full opacity
          d3.select(this).style('opacity', 1);
          d3.select(this).select('circle')
            .attr('stroke', '#FFC107')
            .attr('stroke-width', 6);
        } else if(isIndirectIncoming) {
          // Indirect incoming - cyan, slightly shaded
          d3.select(this).style('opacity', 0.8);
          d3.select(this).select('circle')
            .attr('stroke', '#00BCD4')
            .attr('stroke-width', 6);
        } else {
          // Other nodes - very transparent
          d3.select(this).style('opacity', 0.2);
        }
      });
      
      // Highlight links
      link.each(function(linkData) {
        const isOutgoing = linkData.source === nodeId;
        const isIncoming = linkData.target === nodeId;
        
        if(isOutgoing) {
          d3.select(this).style('opacity', 1).attr('stroke','#9C27B0').attr('stroke-width', 4);
        } else if(isIncoming) {
          d3.select(this).style('opacity', 0.7).attr('stroke','#00BCD4').attr('stroke-width', 4);
        } else {
          d3.select(this).style('opacity', 0.2);
        }
      });
      
      // Highlight arrows
      container.selectAll('.arrow-head').each(function(linkData) {
        const isOutgoing = linkData && linkData.source === nodeId;
        const isIncoming = linkData && linkData.target === nodeId;
        
        if(isOutgoing) {
          d3.select(this).style('opacity', 1).attr('fill','#9C27B0');
        } else if(isIncoming) {
          d3.select(this).style('opacity', 0.7).attr('fill','#00BCD4');
        } else {
          d3.select(this).style('opacity', 0.2);
        }
      });
      
      // Highlight current node border
      d3.select(this).select('circle')
        .attr('stroke','#000')
        .attr('stroke-width', 6);
      
      // Highlight current node border
      d3.select(this).select('circle')
        .attr('stroke','#000')
        .attr('stroke-width', 6);
    }).on('mouseout', function() {
      // Don't reset if locked
      if(isLocked) return;
      
      // Reset all opacities
      node.style('opacity', 1);
      link.style('opacity', 1);
      container.selectAll('.arrow-head').style('opacity', 1);
      
      // Reset colors
      node.selectAll('circle')
        .attr('stroke','#333')
        .attr('stroke-width', 3);
      
      link.attr('stroke','#666').attr('stroke-width', 2);
      container.selectAll('.arrow-head').attr('fill','#666');
    }).on('click', function(event, d) {
      // Prevent opening URL when clicking to lock
      event.stopPropagation();
      
      // Lock the current highlight
      isLocked = true;
      lockedNodeId = d.data.id;
      
      // Show clear button
      d3.select('#clear-lock-btn').style('display', 'block');
      
      // Trigger the highlight effect
      const mouseoverEvent = new MouseEvent('mouseover');
      this.dispatchEvent(mouseoverEvent);
    });

    // Link hover
    link.on('mouseover', function(event, d) {
      // Don't highlight on hover if locked
      if(isLocked) return;
      
      d3.select(this).attr('stroke','#FF9800').attr('stroke-width', 4);
      
      container.selectAll('.arrow-head').each(function(linkData) {
        if(linkData && linkData.source === d.source && linkData.target === d.target) {
          d3.select(this).attr('fill','#FF9800');
        }
      });
      
      node.each(function(nodeData) {
        if(nodeData.data.id === d.source || nodeData.data.id === d.target) {
          d3.select(this).select('circle')
            .attr('stroke','#FF9800')
            .attr('stroke-width', 5);
        }
      });
    }).on('mouseout', function() {
      // Don't reset if locked
      if(isLocked) return;
      
      d3.select(this).attr('stroke','#666').attr('stroke-width', 2);
      container.selectAll('.arrow-head').attr('fill','#666');
      node.selectAll('circle').attr('stroke','#333').attr('stroke-width', 3);
    }).on('click', function(event, d) {
      // Prevent event bubbling
      event.stopPropagation();
      
      // Lock the current link highlight
      isLocked = true;
      lockedNodeId = null; // Clear node lock since we're locking a link
      
      // Show clear button
      d3.select('#clear-lock-btn').style('display', 'block');
      
      // Trigger the highlight effect
      const mouseoverEvent = new MouseEvent('mouseover');
      this.dispatchEvent(mouseoverEvent);
    });

    link.append('title').text(d=>d.label);
    // Center on root node on initial load
    setTimeout(() => {
      const rootNode = hierarchyRoot.descendants().find(n => n.data.id === root.id);
      if(rootNode) {
        const viewportWidth = window.innerWidth;
        const viewportHeight = window.innerHeight;
        const scale = 0.7; // Your desired zoom level
        
        const transform = d3.zoomIdentity
          .translate(
            viewportWidth / 2 - rootNode.x * scale, 
            viewportHeight / 3 - rootNode.y * scale
          )
          .scale(scale);
        
        svg.call(zoom.transform, transform);
      }
    }, 100);
  }
})();
