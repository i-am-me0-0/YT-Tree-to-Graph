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

  // Load graph list and populate dropdown (static copy uses local graphs.json)
  fetch('graphs.json').then(r=>r.json()).then(data => {
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
  }).catch(err => {
    console.error('Failed to load graphs.json', err);
    alert('Failed to load graphs.json. Make sure the file is present.');
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
    
    
    
    
    
    render(graph);
  }

  function truncate(s, n=40){ if(!s) return ''; return s.length>n ? s.slice(0,n-1)+'…' : s; }
  function wrapText(text, maxWidth) {
    const words = text.split(' ');
    const lines = [];
    let currentLine = '';
    let hasMore = false;
    
    words.forEach((word, idx) => {
      if(lines.length >= 2) { hasMore = true; return; }
      if(word.length > maxWidth) {
        if(currentLine) { lines.push(currentLine); currentLine = ''; }
        if(lines.length < 2) { lines.push(word.slice(0, maxWidth - 1) + '…'); hasMore = true; }
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
    if(currentLine && lines.length < 2) { lines.push(currentLine); } else if(currentLine) { hasMore = true; }
    if(hasMore && lines.length > 0) { lines[lines.length - 1] = lines[lines.length - 1] + '…'; }
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
    
    // Update stats display
    const nodeCountEl = document.getElementById('nodeCount'); if(nodeCountEl) nodeCountEl.textContent = nodes.length;
    const totalConnections = nodes.reduce((sum, n) => sum + (n.outgoing ? n.outgoing.length : 0), 0);
    const connEl = document.getElementById('connectionCount'); if(connEl) connEl.textContent = totalConnections;
    
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
    const nodeDepths = new Map();
    const nodeParents = new Map();
    
    const trailerNode = trailerVideoId ? nodes.find(n => n.id === trailerVideoId) : null;
    if (trailerNode) {
      nodeDepths.set(trailerVideoId, -1);
      nodeParents.set(trailerVideoId, null);
    }

    const queue = [{id: root.id, depth: 0, parent: null}];
    nodeDepths.set(root.id, 0);
    while(queue.length > 0) {
      const {id, depth, parent} = queue.shift();
      const node = regularNodes.find(n => n.id === id);
      if(!node) continue;
      if(node.outgoing) {
        node.outgoing.forEach(out => {
          if(!nodeDepths.has(out.to)) {
            nodeDepths.set(out.to, depth + 1);
            nodeParents.set(out.to, id);
            queue.push({id: out.to, depth: depth + 1, parent: id});
          }
        });
      }
    }

    const buildTree = (nodeId) => {
      const node = regularNodes.find(n => n.id === nodeId);
      if(!node) return null;
      const children = [];
      nodeParents.forEach((parentId, childId) => {
        if(parentId === nodeId) {
          const childTree = buildTree(childId);
          if(childTree) children.push(childTree);
        }
      });
      return {...node, children};
    };

    const completeTree = buildTree(root.id);
    const hierarchyRoot = d3.hierarchy(completeTree);

    const part2HierarchyNode = hierarchyRoot.descendants().find(n => n.data.id === part2VideoId);
    const part2NodeIds = new Set();
    if(part2HierarchyNode) {
      part2HierarchyNode.descendants().forEach(n => { part2NodeIds.add(n.data.id); });
    }

    const layerHeight = 220;
    const nodeSpacing = 200;
    const part2Offset = 100;

    const layers = {};
    hierarchyRoot.descendants().forEach(node => { if(!layers[node.depth]) layers[node.depth] = []; layers[node.depth].push(node); });

    if (trailerNode) {
      const trailerHierarchyNode = { data: trailerNode, depth: -1, y: -150, x: width / 2 };
      if (!layers[-1]) layers[-1] = [];
      layers[-1].push(trailerHierarchyNode);
    }

    const bonusNodes = [];
    if (bonusVideoIds.size > 0) {
      const bonusStartX = width / 2 + 280;
      const bonusStartY = 50;
      const bonusHorizontalSpacing = 220;
      let index = 0;
      bonusVideoIds.forEach((bonusId) => {
        const bonusNode = nodes.find(n => n.id === bonusId);
        if (bonusNode) {
          const enhancedNode = {...bonusNode};
          const originalDesc = bonusNode.clean_description || 'No Description';
          enhancedNode.clean_description = `${originalDesc}`;
          bonusNodes.push({ data: enhancedNode, depth: 0, y: bonusStartY, x: bonusStartX + (index * bonusHorizontalSpacing) });
          index++;
        }
      });
    }

    const nodesConnectingToPart2 = new Set();
    if(part2VideoId) {
      regularNodes.forEach(node => {
        if(node.outgoing) {
          node.outgoing.forEach(out => { if(out.to === part2VideoId) nodesConnectingToPart2.add(node.id); });
        }
      });
    }

    let maxDepthBeforePart2 = 0;
    if(part2VideoId && nodesConnectingToPart2.size > 0) {
      hierarchyRoot.descendants().forEach(node => {
        if(nodesConnectingToPart2.has(node.data.id) && !part2NodeIds.has(node.data.id)) {
          maxDepthBeforePart2 = Math.max(maxDepthBeforePart2, node.depth);
        }
      });
    }
    const part2StartDepth = maxDepthBeforePart2 + 1;

    Object.keys(layers).forEach(depth => {
      const depthNodes = layers[depth];
      depthNodes.forEach((node, i) => {
        const isPart2Node = part2NodeIds.has(node.data.id);
        if(node.data.id === trailerVideoId) {
          node.y = -150; node.x = width / 2;
        } else if(node.data.id === part2VideoId) {
          node.y = part2StartDepth * layerHeight + part2Offset + 100; node.x = width / 2;
        } else if(isPart2Node) {
          const part2Node = hierarchyRoot.descendants().find(n => n.data.id === part2VideoId);
          const relativeDepth = node.depth - part2Node.depth;
          node.y = part2StartDepth * layerHeight + part2Offset + 100 + relativeDepth * layerHeight;
          node.x = (i - depthNodes.length / 2) * nodeSpacing + width / 2;
        } else {
          node.y = node.depth * layerHeight + 100;
          node.x = (i - depthNodes.length / 2) * nodeSpacing + width / 2;
        }
      });
    });

    const hasIncoming = new Set(links.map(l=>l.target));
    const hasOutgoing = new Set(links.map(l=>l.source));
    const startNodes = regularNodes.filter(n => !hasIncoming.has(n.id));
    const endNodes = regularNodes.filter(n => !hasOutgoing.has(n.id));

    const part2ConnectionNodes = new Set();
    if(part2VideoId) {
      regularNodes.forEach(node => {
        if(node.outgoing) { node.outgoing.forEach(out => { if(out.to === part2VideoId) part2ConnectionNodes.add(node.id); }); }
      });
    }

    const loopBackNodes = new Set();
    regularNodes.forEach(node => {
      if(node.outgoing) {
        node.outgoing.forEach(out => {
          if(out.to === root.id || out.to === part2VideoId) {
            if(node.id !== root.id && node.id !== part2VideoId) loopBackNodes.add(node.id);
          }
        });
      }
    });

    const nodeRadius = 85;

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
        const allNodesForLookup = hierarchyRoot.descendants();
        if (trailerNode && layers[-1] && layers[-1].length > 0) { allNodesForLookup.push(layers[-1][0]); }
        const sourceNode = allNodesForLookup.find(n => n.data.id === d.source);
        const targetNode = allNodesForLookup.find(n => n.data.id === d.target);
        if(!sourceNode || !targetNode) return '';
        const sx = sourceNode.x; const sy = sourceNode.y + nodeRadius; const tx = targetNode.x; const ty = targetNode.y - nodeRadius - 5;
        return `M${sx},${sy} C${sx},${sy + 60} ${tx},${ty - 60} ${tx},${ty}`;
      });

    const node = container.append('g').attr('class','nodes')
      .selectAll('g')
      .data(() => {
        const allNodes = hierarchyRoot.descendants();
        if (trailerNode && layers[-1] && layers[-1].length > 0) { allNodes.push(layers[-1][0]); }
        if (bonusNodes.length > 0) { allNodes.push(...bonusNodes); }
        return allNodes;
      })
      .enter().append('g')
      .attr('transform', d => `translate(${d.x},${d.y})`)
      .attr('class', 'node-group')
      .style('cursor','pointer');

    node.on('dblclick', (event, d) => { event.stopPropagation(); window.open(d.data.url,'_blank'); });

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
        isLocked = false; lockedNodeId = null; d3.select(this).style('display', 'none'); node.style('opacity', 1); link.style('opacity', 1); container.selectAll('.arrow-head').style('opacity', 1); node.selectAll('circle').attr('stroke','#333').attr('stroke-width', 3); link.attr('stroke','#666').attr('stroke-width', 2); container.selectAll('.arrow-head').attr('fill','#666');
      });

    node.append('circle').attr('r', nodeRadius).attr('fill', d => {
      if(bonusVideoIds.has(d.data.id)) return '#FFA000';
      if(d.data.id === trailerVideoId) return '#81C784';
      if(d.data.id === root.id) return '#4CAF50';
      if(d.data.id === part2VideoId) return '#4CAF50';
      if(stopVideoIds.has(d.data.id)) return '#9C27B0';
      if(part2ConnectionNodes.has(d.data.id)) return '#FF9800';
      if(loopBackNodes.has(d.data.id)) return '#E91E63';
      if(endNodes.find(e=>e.id===d.data.id)) return '#f44336';
      return '#2196F3';
    }).attr('stroke','#333').attr('stroke-width', 3).attr('fill-opacity', 0.9).attr('class', 'node-circle');

    node.each(function(d) {
      const g = d3.select(this);
      const titleLines = wrapText(d.data.title, 18);
      titleLines.forEach((line, i) => {
        g.append('text').attr('y', -50 + i*11).attr('text-anchor','middle').attr('font-size',10).attr('font-weight','bold').attr('fill','#fff').text(line);
      });
    });

    const imgWidth = 80; const imgHeight = 45;
    node.append('image').attr('href', d=>d.data.thumbnail).attr('x', -imgWidth/2).attr('y', -25).attr('width', imgWidth).attr('height', imgHeight).attr('clip-path', 'inset(0 round 6px)').attr('preserveAspectRatio', 'xMidYMid slice');

    node.each(function(d) {
      const desc = d.data.clean_description || ''; if(desc) {
        const lines = wrapText(desc, 20); const g = d3.select(this);
        lines.forEach((line, i) => { g.append('text').attr('y', 55 + i*10).attr('text-anchor','middle').attr('font-size',8).attr('fill','#fff').text(line); });
      }
    });

    node.append('title').text(d=>`${d.data.title}\n${d.data.clean_description || ''}`);

    node.on('mouseover', function(event, d) {
      if(isLocked) return;
      const nodeId = d.data.id;
      const outgoingIds = d.data.outgoing ? d.data.outgoing.map(o => o.to) : [];
      const directIncomingIds = new Set(); if(d.data.incoming_from) { d.data.incoming_from.forEach(incoming => { directIncomingIds.add(incoming.from); }); }
      const allIncomingIds = new Set(); const visited = new Set();
      function findAllIncoming(currentNodeId, depth = 0) { if(depth > 10 || visited.has(currentNodeId)) return; visited.add(currentNodeId); let currentNode = null; node.each(function(nodeData) { if(nodeData.data.id === currentNodeId) currentNode = nodeData.data; }); if(currentNode && currentNode.incoming_from) {currentNode.incoming_from.forEach(incoming => {if(!loopBackNodes.has(incoming.from)) {allIncomingIds.add(incoming.from);findAllIncoming(incoming.from, depth + 1);}});}}directIncomingIds.forEach(incomingId => {findAllIncoming(incomingId);});
      node.each(function(nodeData) {
        const isOutgoing = outgoingIds.includes(nodeData.data.id);
        const isDirectIncoming = directIncomingIds.has(nodeData.data.id);
        const isIndirectIncoming = allIncomingIds.has(nodeData.data.id) && !isDirectIncoming;
        const isCurrent = nodeData.data.id === nodeId;
        if(isCurrent) { d3.select(this).style('opacity', 1); } else if(isOutgoing) { d3.select(this).style('opacity', 1); d3.select(this).select('circle').attr('stroke', '#9C27B0').attr('stroke-width', 6); } else if(isDirectIncoming) { d3.select(this).style('opacity', 1); d3.select(this).select('circle').attr('stroke', '#FFC107').attr('stroke-width', 6); } else if(isIndirectIncoming) { d3.select(this).style('opacity', 0.8); d3.select(this).select('circle').attr('stroke', '#00BCD4').attr('stroke-width', 6); } else { d3.select(this).style('opacity', 0.2); }
      });
      link.each(function(linkData) { const isOutgoing = linkData.source === nodeId; const isIncoming = linkData.target === nodeId; if(isOutgoing) { d3.select(this).style('opacity', 1).attr('stroke','#9C27B0').attr('stroke-width', 4); } else if(isIncoming) { d3.select(this).style('opacity', 0.7).attr('stroke','#00BCD4').attr('stroke-width', 4); } else { d3.select(this).style('opacity', 0.2); } });
      container.selectAll('.arrow-head').each(function(linkData) { const isOutgoing = linkData && linkData.source === nodeId; const isIncoming = linkData && linkData.target === nodeId; if(isOutgoing) { d3.select(this).style('opacity', 1).attr('fill','#9C27B0'); } else if(isIncoming) { d3.select(this).style('opacity', 0.7).attr('fill','#00BCD4'); } else { d3.select(this).style('opacity', 0.2); } });
      d3.select(this).select('circle').attr('stroke','#000').attr('stroke-width', 6);
    }).on('mouseout', function() { if(isLocked) return; node.style('opacity', 1); link.style('opacity', 1); container.selectAll('.arrow-head').style('opacity', 1); node.selectAll('circle').attr('stroke','#333').attr('stroke-width', 3); link.attr('stroke','#666').attr('stroke-width', 2); container.selectAll('.arrow-head').attr('fill','#666'); }).on('click', function(event, d) { event.stopPropagation(); isLocked = true; lockedNodeId = d.data.id; d3.select('#clear-lock-btn').style('display', 'block'); const mouseoverEvent = new MouseEvent('mouseover'); this.dispatchEvent(mouseoverEvent); });

    link.on('mouseover', function(event, d) { if(isLocked) return; d3.select(this).attr('stroke','#FF9800').attr('stroke-width', 4); container.selectAll('.arrow-head').each(function(linkData) { if(linkData && linkData.source === d.source && linkData.target === d.target) { d3.select(this).attr('fill','#FF9800'); } }); node.each(function(nodeData) { if(nodeData.data.id === d.source || nodeData.data.id === d.target) { d3.select(this).select('circle').attr('stroke','#FF9800').attr('stroke-width', 5); } }); }).on('mouseout', function() { if(isLocked) return; d3.select(this).attr('stroke','#666').attr('stroke-width', 2); container.selectAll('.arrow-head').attr('fill','#666'); node.selectAll('circle').attr('stroke','#333').attr('stroke-width', 3); }).on('click', function(event, d) { event.stopPropagation(); isLocked = true; lockedNodeId = null; d3.select('#clear-lock-btn').style('display', 'block'); const mouseoverEvent = new MouseEvent('mouseover'); this.dispatchEvent(mouseoverEvent); });

    link.append('title').text(d=>d.label);
    setTimeout(() => {const rootNode = hierarchyRoot.descendants().find(n => n.data.id === root.id);if(rootNode) {const viewportWidth = window.innerWidth;const viewportHeight = window.innerHeight;const scale = 0.7;const transform = d3.zoomIdentity.translate(viewportWidth / 2 - rootNode.x * scale, viewportHeight / 3 - rootNode.y * scale).scale(scale);svg.call(zoom.transform, transform);}}, 100);
  }
})();
