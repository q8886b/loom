import axios from 'axios'

const api = axios.create({ baseURL: '/api', timeout: 30000 })

export const getStats = () => api.get('/stats').then((r) => r.data)
export const getTags = () => api.get('/tags').then((r) => r.data)
export const getVersion = () => api.get('/version').then((r) => r.data)
export const getCard = (id) => api.get(`/cards/${encodeURIComponent(id)}`).then((r) => r.data)
export const getCardsByNs = (ns, tag) =>
  api.get(`/cards/by_ns/${encodeURIComponent(ns)}`, { params: { tag } }).then((r) => r.data)
export const getTree = (ns, tag) => api.get('/tree', { params: { ns, tag } }).then((r) => r.data)
export const getGraphOverview = (maxDepth = 1) =>
  api.get('/graph/overview', { params: { max_depth: maxDepth } }).then((r) => r.data)
export const getGraphByNs = (ns, tag, view = 'all', layer = '', include = '', limit = 0) =>
  api.get(`/graph/by_ns/${encodeURIComponent(ns)}`, { params: { tag, view, layer, include, limit } }).then((r) => r.data)
export const getGraphCluster = (id, depth = 2) =>
  api.get(`/graph/cluster/${encodeURIComponent(id)}`, { params: { depth } }).then((r) => r.data)
export const getGraphExpand = (id) =>
  api.get(`/graph/expand/${encodeURIComponent(id)}`).then((r) => r.data)
export const search = (q, top = 30, tag = '') =>
  api.get('/search', { params: { q, top, tag } }).then((r) => r.data)
