/**
 * 布局算法
 *
 * 两种模式：
 * 1. 有层级结构时：水平树布局（根在左，children 往右）
 * 2. 扁平结构时：力导向模拟布局（按 link 关系聚合）
 *
 * 力导向布局的核心思想：
 * - 有 link 连接的节点互相吸引（距离近）
 * - 所有节点互相排斥（避免重叠）
 * - 出入度高的节点自然聚集在中心
 * - 稀疏节点推到边缘
 * - 整体比例接近屏幕比例（宽略大于高）
 */

const NODE_W = 200
const NODE_H = 56
const H_GAP = 80    // 水平间距（层级之间）
const V_GAP = 16    // 垂直间距（同级兄弟之间）

/**
 * 计算子树高度（像素），用于垂直居中对齐
 */
function subtreeHeight(node, expanded) {
  if (!expanded.has(node.id)) {
    return NODE_H
  }
  const children = node.children || []
  if (!children.length) return NODE_H
  let total = 0
  for (const child of children) {
    total += subtreeHeight(child, expanded)
  }
  total += (children.length - 1) * V_GAP
  return Math.max(NODE_H, total)
}

/**
 * 递归计算每个节点的后代总数（含自身）
 */
function descendantCount(node) {
  const children = node.children || []
  let count = 1
  for (const child of children) {
    count += descendantCount(child)
  }
  return count
}

/**
 * 主布局函数
 *
 * @param {Array} roots - 树的根节点数组（来自 /api/tree）
 * @param {Set} expanded - 已展开的节点 ID 集合
 * @param {String} selectedId - 当前选中的节点 ID
 * @returns {{ nodes: Array, edges: Array }} Vue Flow 格式的节点和边
 */
export function layoutTree(roots, expanded, selectedId, linkEdges) {
  if (!roots || !roots.length) return { nodes: [], edges: [] }

  // 检测是否为扁平结构（所有 root 都无 children）
  const hasAnyChildren = roots.some(r => (r.children || []).length > 0)

  if (!hasAnyChildren) {
    // 扁平结构
    if (roots.length > 200) {
      // 大量扁平节点：直接用紧凑网格（力导向 O(n^2) 太慢会卡住）
      return layoutCompactGrid(roots)
    }
    // 少量扁平节点：使用力导向模拟布局
    return layoutForceDirected(roots, linkEdges)
  }

  // 有层级结构：如果 root 数量很多（>20），用多列网格排列 root，
  // 每个 root 带自己的子树水平展开。避免 357 个 root 排成一列的长条问题。
  const nodes = []
  const edges = []

  if (roots.length > 20) {
    // 多列布局：将 roots 分成多列，每列内垂直排列
    // 对于大 namespace（未展开状态），roots 都是单个节点（无子树）
    // 使用紧凑的网格排列，让 fitView 能展示在一屏内
    const allCollapsed = !roots.some(r => expanded.has(r.id) && (r.children || []).length > 0)

    if (allCollapsed) {
      // 所有 root 都折叠：使用紧凑网格
      // 目标：让 fitView 在 minZoom=0.45 时能完整显示
      // 视口约 880x750px，除以 0.45 = 可显示 1955x1666px 的布局
      const TARGET_W = 1800
      const CELL_W = NODE_W + 25
      const CELL_H = NODE_H + 16
      const COLS = Math.min(Math.floor(TARGET_W / CELL_W), Math.max(4, Math.ceil(Math.sqrt(roots.length * 1.2))))

      for (let i = 0; i < roots.length; i++) {
        const col = i % COLS
        const row = Math.floor(i / COLS)
        const root = roots[i]
        const totalDescendants = descendantCount(root) - 1

        nodes.push({
          id: root.id,
          type: 'card',
          position: { x: col * CELL_W, y: row * CELL_H },
          data: {
            title: root.title,
            cardType: root.type,
            layer: root.layer,
            namespace: root.namespace,
            hasChildren: (root.children || []).length > 0,
            isExpanded: false,
            childCount: totalDescendants,
            isSelected: false,
          },
        })
      }
    } else {
      // 部分展开：多列布局，每列留出子树空间
      const COLS = Math.max(2, Math.ceil(Math.sqrt(roots.length / 3)))
      const COL_WIDTH = (NODE_W + H_GAP) * 3 + 60
      let colY = new Array(COLS).fill(0)

      const rootsWithHeight = roots.map(r => ({
        root: r,
        height: subtreeHeight(r, expanded),
      }))

      for (const { root, height } of rootsWithHeight) {
        const col = colY.indexOf(Math.min(...colY))
        const xOffset = col * COL_WIDTH
        const yStart = colY[col]
        layoutNodeOffset(root, 0, yStart, yStart + height, null, nodes, edges, expanded, xOffset)
        colY[col] += height + V_GAP * 2
      }
    }
  } else {
    // 少量 root：传统单列水平树
    let cursorY = 0
    for (const root of roots) {
      const height = subtreeHeight(root, expanded)
      layoutNode(root, 0, cursorY, cursorY + height, null, nodes, edges, expanded)
      cursorY += height + V_GAP * 2
    }
  }

  return { nodes, edges }
}

/**
 * 力导向模拟布局：扁平结构时使用。
 * 按 link 关系聚合——出入度高的节点居中，稀疏节点边缘。
 * 整体比例接近 16:10（屏幕宽高比）。
 *
 * 算法：简单的 N-body 模拟，迭代若干轮收敛。
 * - 所有节点间有排斥力（避免重叠）
 * - 有 link 连接的节点间有吸引力（拉近）
 * - 出入度高的节点初始放在中心附近
 */
function layoutForceDirected(roots, linkEdges) {
  const nodes = []
  const edges = []
  const sorted = [...roots].sort((a, b) => a.id.localeCompare(b.id))
  const n = sorted.length
  if (!n) return { nodes, edges }

  // 目标画布尺寸：宽略大于高（~16:10），但不要太大
  // 48 节点时大约 1600x1000 范围
  const targetW = Math.max(1200, Math.sqrt(n) * 220)
  const targetH = targetW / 1.5

  // 计算每个节点的度数（用于初始位置）
  const degree = new Map()
  for (const node of sorted) degree.set(node.id, 0)
  const links = linkEdges || []
  const idSet = new Set(sorted.map(r => r.id))
  for (const e of links) {
    if (idSet.has(e.source) && idSet.has(e.target)) {
      degree.set(e.source, (degree.get(e.source) || 0) + 1)
      degree.set(e.target, (degree.get(e.target) || 0) + 1)
    }
  }

  // 初始位置：度数高的靠中心，低的散开（使用确定性种子，避免每次布局不同）
  const maxDeg = Math.max(1, ...degree.values())
  const positions = new Map()
  const idxMap = new Map()
  sorted.forEach((node, i) => {
    idxMap.set(node.id, i)
    const deg = degree.get(node.id) || 0
    const centrality = deg / maxDeg  // 0~1, 1=最中心
    // 确定性初始位置：基于 index 的均匀分布 + centrality 决定半径
    const angle = (i / n) * Math.PI * 2
    const radius = (1 - centrality * 0.7) * Math.min(targetW, targetH) * 0.4
    // 用 node index 做确定性抖动（代替 Math.random）
    const jitterX = ((i * 7 + 13) % 31 - 15) * 3
    const jitterY = ((i * 11 + 7) % 23 - 11) * 3
    positions.set(node.id, {
      x: targetW / 2 + Math.cos(angle) * radius + jitterX,
      y: targetH / 2 + Math.sin(angle) * radius + jitterY,
    })
  })

  // 力导向迭代
  const ITERATIONS = 80
  const REPULSION = 8000
  const ATTRACTION = 0.008
  const DAMPING = 0.92
  const MIN_DIST = NODE_W * 0.8

  const velocities = new Map()
  for (const node of sorted) velocities.set(node.id, { x: 0, y: 0 })

  for (let iter = 0; iter < ITERATIONS; iter++) {
    const temp = 1 - iter / ITERATIONS  // cooling

    // 排斥力（所有节点对）
    for (let i = 0; i < n; i++) {
      for (let j = i + 1; j < n; j++) {
        const a = sorted[i].id
        const b = sorted[j].id
        const pa = positions.get(a)
        const pb = positions.get(b)
        let dx = pa.x - pb.x
        let dy = pa.y - pb.y
        let dist = Math.sqrt(dx * dx + dy * dy)
        if (dist < 1) { dx = 1; dy = 1; dist = 1.41 }
        if (dist < MIN_DIST * 3) {
          const force = REPULSION / (dist * dist)
          const fx = (dx / dist) * force * temp
          const fy = (dy / dist) * force * temp
          const va = velocities.get(a)
          const vb = velocities.get(b)
          va.x += fx; va.y += fy
          vb.x -= fx; vb.y -= fy
        }
      }
    }

    // 吸引力（有 link 连接的节点对）
    for (const e of links) {
      if (!idSet.has(e.source) || !idSet.has(e.target)) continue
      const pa = positions.get(e.source)
      const pb = positions.get(e.target)
      if (!pa || !pb) continue
      const dx = pb.x - pa.x
      const dy = pb.y - pa.y
      const dist = Math.sqrt(dx * dx + dy * dy)
      if (dist < 1) continue
      const force = dist * ATTRACTION * temp
      const fx = (dx / dist) * force
      const fy = (dy / dist) * force
      const va = velocities.get(e.source)
      const vb = velocities.get(e.target)
      va.x += fx; va.y += fy
      vb.x -= fx; vb.y -= fy
    }

    // 向中心轻微引力（防止飘散）
    for (const node of sorted) {
      const p = positions.get(node.id)
      const v = velocities.get(node.id)
      const cx = targetW / 2 - p.x
      const cy = targetH / 2 - p.y
      v.x += cx * 0.0005 * temp
      v.y += cy * 0.0005 * temp
    }

    // 应用速度
    for (const node of sorted) {
      const p = positions.get(node.id)
      const v = velocities.get(node.id)
      p.x += v.x
      p.y += v.y
      v.x *= DAMPING
      v.y *= DAMPING
    }
  }

  // 归一化：将位置缩放到合理范围，保持 ~16:10 比例
  let minX = Infinity, minY = Infinity, maxX = -Infinity, maxY = -Infinity
  for (const p of positions.values()) {
    if (p.x < minX) minX = p.x
    if (p.y < minY) minY = p.y
    if (p.x > maxX) maxX = p.x
    if (p.y > maxY) maxY = p.y
  }
  const rangeX = maxX - minX || 1
  const rangeY = maxY - minY || 1
  const finalW = Math.max(rangeX, 1200)
  const finalH = Math.max(rangeY, 800)

  for (const node of sorted) {
    const p = positions.get(node.id)
    nodes.push({
      id: node.id,
      type: 'card',
      position: {
        x: p.x - minX,
        y: p.y - minY,
      },
      data: {
        title: node.title,
        cardType: node.type,
        layer: node.layer,
        namespace: node.namespace,
        hasChildren: false,
        isExpanded: false,
        childCount: 0,
        isSelected: false,
      },
    })
  }

  return { nodes, edges }
}

/**
 * 紧凑网格布局：大量扁平节点（>200）时使用。
 * 简单的行列排列，避免 O(n^2) 的力导向计算。
 */
function layoutCompactGrid(roots) {
  const nodes = []
  const edges = []
  const sorted = [...roots].sort((a, b) => a.id.localeCompare(b.id))
  const n = sorted.length

  const TARGET_W = 2400
  const CELL_W = NODE_W + 30
  const CELL_H = NODE_H + 20
  const COLS = Math.min(Math.floor(TARGET_W / CELL_W), Math.ceil(Math.sqrt(n * 1.4)))

  for (let i = 0; i < n; i++) {
    const col = i % COLS
    const row = Math.floor(i / COLS)
    const node = sorted[i]
    nodes.push({
      id: node.id,
      type: 'card',
      position: { x: col * CELL_W, y: row * CELL_H },
      data: {
        title: node.title,
        cardType: node.type,
        layer: node.layer,
        namespace: node.namespace,
        hasChildren: false,
        isExpanded: false,
        childCount: 0,
        isSelected: false,
      },
    })
  }

  return { nodes, edges }
}

function layoutNode(node, depth, yMin, yMax, parentId, nodes, edges, expanded) {
  layoutNodeOffset(node, depth, yMin, yMax, parentId, nodes, edges, expanded, 0)
}

function layoutNodeOffset(node, depth, yMin, yMax, parentId, nodes, edges, expanded, xOffset) {
  const x = xOffset + depth * (NODE_W + H_GAP)
  const y = (yMin + yMax) / 2 - NODE_H / 2

  const isExpanded = expanded.has(node.id)
  const children = node.children || []
  const hasChildren = children.length > 0
  const totalDescendants = descendantCount(node) - 1

  nodes.push({
    id: node.id,
    type: 'card',
    position: { x, y },
    data: {
      title: node.title,
      cardType: node.type,
      layer: node.layer,
      namespace: node.namespace,
      hasChildren,
      isExpanded,
      childCount: totalDescendants,
      isSelected: false,
    },
  })

  if (parentId) {
    edges.push({
      id: `e-${parentId}-${node.id}`,
      source: parentId,
      target: node.id,
      type: 'hierarchy',
      data: { kind: 'hierarchy' },
    })
  }

  if (isExpanded && children.length) {
    let childY = yMin
    for (const child of children) {
      const childH = subtreeHeight(child, expanded)
      layoutNodeOffset(child, depth + 1, childY, childY + childH, node.id, nodes, edges, expanded, xOffset)
      childY += childH + V_GAP
    }
  }
}

/**
 * 计算 link 边（跨树关联）
 * 只保留两端都在当前可见节点中的 link
 *
 * @param {Array} linkEdges - 后端返回的 link_edges [{source, target}]
 * @param {Set} visibleIds - 当前画布上可见的节点 ID 集合
 * @returns {Array} Vue Flow 格式的 link 边
 */
export function layoutLinks(linkEdges, visibleIds) {
  const edges = []
  for (const e of linkEdges) {
    const bothVisible = visibleIds.has(e.source) && visibleIds.has(e.target)
    if (bothVisible) {
      edges.push({
        id: `link-${e.source}-${e.target}`,
        source: e.source,
        target: e.target,
        type: 'link',
        data: { kind: 'link' },
      })
    }
  }
  return edges
}

/**
 * 计算跨域 link（飞向停靠区的）
 * 返回按目标域分组的外部连接信息
 *
 * @param {Array} allLinkEdges - 所有 link 边
 * @param {Set} visibleIds - 当前画布上可见的节点 ID
 * @param {Object} cardIndex - id → card 数据的映射（用于获取标题等）
 * @returns {Object} { [namespace]: { count, cards: [{id, title}] } }
 */
export function computeDockLinks(allLinkEdges, visibleIds, cardIndex) {
  const dock = {}
  for (const e of allLinkEdges) {
    let externalId = null
    if (visibleIds.has(e.source) && !visibleIds.has(e.target)) {
      externalId = e.target
    } else if (visibleIds.has(e.target) && !visibleIds.has(e.source)) {
      externalId = e.source
    }
    if (!externalId) continue

    const ns = externalId.includes(':') ? externalId.split(':')[0] : '_other'
    if (!dock[ns]) dock[ns] = { count: 0, cards: [] }
    dock[ns].count++
    const card = cardIndex[externalId]
    dock[ns].cards.push({
      id: externalId,
      title: card?.title || externalId,
      type: card?.type || '',
      layer: card?.layer || '',
    })
  }
  return dock
}

/**
 * 聚焦模式布局（力导向辐射）
 * 中心卡固定在原点，邻居通过力导向模拟分散在周围。
 * - 所有邻居被中心卡吸引（保持在合理距离）
 * - 邻居之间互相排斥（避免重叠）
 * - 有 link/hierarchy 连接的邻居之间轻微吸引（聚簇）
 * - 同域邻居互相吸引（视觉分组）
 * 结果：自然聚合、线条不穿越节点、有呼吸感
 */
export function layoutFocus(centerCard, neighbors, hierarchyEdges, linkEdges) {
  const nodes = []
  const edges = []
  const n = neighbors.length

  // 中心节点固定在原点
  nodes.push({
    id: centerCard.id,
    type: 'card-focus-center',
    position: { x: 0, y: 0 },
    data: {
      title: centerCard.title,
      cardType: centerCard.type,
      layer: centerCard.layer,
      namespace: centerCard.namespace,
      isCenter: true,
    },
  })

  if (!n) {
    // 无邻居，只返回中心节点
    for (const e of linkEdges) {
      edges.push({ id: `link-${e.source}-${e.target}`, source: e.source, target: e.target, type: 'link', data: { kind: 'link' } })
    }
    return { nodes, edges }
  }

  // 构建邻居间的连接关系（用于力导向的吸引力）
  const neighborIds = new Set(neighbors.map(nb => nb.id))
  const neighborEdges = []
  for (const e of [...hierarchyEdges, ...linkEdges]) {
    if (neighborIds.has(e.source) && neighborIds.has(e.target)) {
      neighborEdges.push(e)
    }
  }

  // 计算每个邻居与中心的 link 数量（用于决定初始距离）
  const centerLinks = new Map()
  for (const nb of neighbors) centerLinks.set(nb.id, 0)
  for (const e of linkEdges) {
    if (e.source === centerCard.id && centerLinks.has(e.target)) {
      centerLinks.set(e.target, (centerLinks.get(e.target) || 0) + 1)
    }
    if (e.target === centerCard.id && centerLinks.has(e.source)) {
      centerLinks.set(e.source, (centerLinks.get(e.source) || 0) + 1)
    }
  }

  // 初始位置：按域分组，均匀分布在环上，半径根据节点数量动态调整
  const BASE_RADIUS = Math.max(300, Math.sqrt(n) * 120)
  const positions = new Map()

  // 按域分组以分配初始角度扇区
  const byNs = new Map()
  for (const nb of neighbors) {
    const ns = nb.namespace || (nb.id.includes(':') ? nb.id.split(':')[0] : '_other')
    if (!byNs.has(ns)) byNs.set(ns, [])
    byNs.get(ns).push(nb)
  }

  const nsKeys = [...byNs.keys()].sort()
  let globalIdx = 0
  nsKeys.forEach((ns, nsIdx) => {
    const group = byNs.get(ns)
    const sectorStart = (nsIdx / nsKeys.length) * Math.PI * 2 - Math.PI / 2
    const sectorSize = (1 / nsKeys.length) * Math.PI * 2

    group.forEach((nb, i) => {
      const angle = sectorStart + (i + 0.5) / group.length * sectorSize
      const radius = BASE_RADIUS * (0.6 + 0.4 * (1 - (centerLinks.get(nb.id) || 0) / Math.max(1, ...centerLinks.values())))
      const jitterR = ((globalIdx * 13 + 7) % 17 - 8) * 8
      positions.set(nb.id, {
        x: Math.cos(angle) * (radius + jitterR),
        y: Math.sin(angle) * (radius + jitterR),
      })
      globalIdx++
    })
  })

  // 力导向迭代
  const ITERATIONS = 60
  const REPULSION = 12000       // 邻居间排斥
  const CENTER_PULL = 0.003     // 向中心拉力（防止飘散）
  const NEIGHBOR_ATTRACT = 0.01 // 有连接的邻居间吸引
  const NS_ATTRACT = 0.002      // 同域轻微吸引
  const DAMPING = 0.9
  const MIN_DIST = NODE_W * 1.2 // 最小间距（避免重叠）
  const CENTER_REPEL = 30000    // 中心节点的排斥力（让邻居不要太近）
  const CENTER_MIN = NODE_W * 1.5

  const velocities = new Map()
  for (const nb of neighbors) velocities.set(nb.id, { x: 0, y: 0 })

  for (let iter = 0; iter < ITERATIONS; iter++) {
    const temp = 1 - iter / ITERATIONS * 0.7 // cooling but not too aggressive

    // 邻居间排斥
    for (let i = 0; i < n; i++) {
      for (let j = i + 1; j < n; j++) {
        const a = neighbors[i].id
        const b = neighbors[j].id
        const pa = positions.get(a)
        const pb = positions.get(b)
        let dx = pa.x - pb.x
        let dy = pa.y - pb.y
        let dist = Math.sqrt(dx * dx + dy * dy)
        if (dist < 1) { dx = 1; dy = 0.5; dist = 1.1 }
        if (dist < MIN_DIST * 2.5) {
          const force = REPULSION / (dist * dist) * temp
          const fx = (dx / dist) * force
          const fy = (dy / dist) * force
          velocities.get(a).x += fx
          velocities.get(a).y += fy
          velocities.get(b).x -= fx
          velocities.get(b).y -= fy
        }
      }
    }

    // 中心节点排斥（让邻居不要挤到中心）
    for (const nb of neighbors) {
      const p = positions.get(nb.id)
      const v = velocities.get(nb.id)
      const dist = Math.sqrt(p.x * p.x + p.y * p.y)
      if (dist < CENTER_MIN * 2) {
        const force = CENTER_REPEL / (dist * dist + 1) * temp
        const dx = p.x / (dist || 1)
        const dy = p.y / (dist || 1)
        v.x += dx * force
        v.y += dy * force
      }
    }

    // 向中心拉力（防止飘散到无穷远）
    for (const nb of neighbors) {
      const p = positions.get(nb.id)
      const v = velocities.get(nb.id)
      v.x -= p.x * CENTER_PULL * temp
      v.y -= p.y * CENTER_PULL * temp
    }

    // 有连接的邻居之间吸引
    for (const e of neighborEdges) {
      const pa = positions.get(e.source)
      const pb = positions.get(e.target)
      if (!pa || !pb) continue
      const dx = pb.x - pa.x
      const dy = pb.y - pa.y
      const dist = Math.sqrt(dx * dx + dy * dy)
      if (dist < 1) continue
      const force = dist * NEIGHBOR_ATTRACT * temp
      const fx = (dx / dist) * force
      const fy = (dy / dist) * force
      velocities.get(e.source).x += fx
      velocities.get(e.source).y += fy
      velocities.get(e.target).x -= fx
      velocities.get(e.target).y -= fy
    }

    // 同域节点轻微吸引（视觉聚类）
    for (const [ns, group] of byNs) {
      if (group.length < 2) continue
      // 计算组质心
      let cx = 0, cy = 0
      for (const nb of group) {
        const p = positions.get(nb.id)
        cx += p.x; cy += p.y
      }
      cx /= group.length; cy /= group.length
      // 向质心轻微拉
      for (const nb of group) {
        const p = positions.get(nb.id)
        const v = velocities.get(nb.id)
        v.x += (cx - p.x) * NS_ATTRACT * temp
        v.y += (cy - p.y) * NS_ATTRACT * temp
      }
    }

    // 应用速度
    for (const nb of neighbors) {
      const p = positions.get(nb.id)
      const v = velocities.get(nb.id)
      p.x += v.x
      p.y += v.y
      v.x *= DAMPING
      v.y *= DAMPING
    }
  }

  // 生成节点
  for (const nb of neighbors) {
    const p = positions.get(nb.id)
    nodes.push({
      id: nb.id,
      type: 'card',
      position: { x: p.x, y: p.y },
      data: {
        title: nb.title,
        cardType: nb.type,
        layer: nb.layer,
        namespace: nb.namespace,
        hasChildren: false,
        isExpanded: false,
        childCount: 0,
        isSelected: false,
      },
    })
  }

  // 边
  for (const e of hierarchyEdges) {
    edges.push({
      id: `e-${e.source}-${e.target}`,
      source: e.source,
      target: e.target,
      type: 'hierarchy',
      data: { kind: 'hierarchy' },
    })
  }
  for (const e of linkEdges) {
    edges.push({
      id: `link-${e.source}-${e.target}`,
      source: e.source,
      target: e.target,
      type: 'link',
      data: { kind: 'link' },
    })
  }

  return { nodes, edges }
}
