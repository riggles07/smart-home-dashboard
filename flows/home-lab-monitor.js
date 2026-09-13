/**
 * Home Lab Monitor Flow
 * Proxmox & Docker monitoring
 */
module.exports = function (RED) {
    "use strict";

    class ProxmoxMonitor extends RED.Node {
        constructor(type, msg, config, node) {
            super(type, msg, config, node);
            this.config = config || {};
            this.proxy = null;
            this.clusterNodes = [];
        }

        init() {
            // Initialize Proxmox proxy
            this.proxy = new ProxmoxProxy(this.config.url, this.config.token);
            
            // Subscribe to cluster events
            this.on('subscribe', (event) => {
                if (event.type === 'cluster-status') {
                    this.updateClusterStatus();
                }
            });

            // Set up auto-refresh
            this.setInterval(this.refresh, this.config.refresh || 30000);
        }

        refresh() {
            // Check Proxmox cluster health
            this.proxy.get('/cluster/status', (err, data) => {
                if (!err) {
                    this.status({
                        fill: 'green',
                        shape: 'dot',
                        text: 'ok'
                    });
                    this.send({ payload: data });
                } else {
                    this.status({
                        fill: 'red',
                        shape: 'ring',
                        text: 'error'
                    });
                }
            });
        }

        getClusterNodes() {
            return this.proxy.get('/cluster/nodes', (err, data) => {
                if (!err) {
                    this.clusterNodes = data.nodes || [];
                    this.status({
                        fill: 'blue',
                        shape: 'dot',
                        text: `${this.clusterNodes.length} nodes`
                    });
                    this.send({ payload: this.clusterNodes });
                }
            });
        }

        getNodeStatus(nodeId) {
            return this.proxy.get(`/nodes/${nodeId}/status`, (err, data) => {
                if (!err) {
                    this.status({
                        fill: data.status === 'running' ? 'green' : 'red',
                        shape: 'dot',
                        text: data.status
                    });
                    this.send({ payload: data });
                }
            });
        }

        getDockerContainers() {
            return this.proxy.get('/docker/containers', (err, data) => {
                if (!err) {
                    const running = data.containers?.filter(c => c.State === 'running') || [];
                    const total = data.containers?.length || 0;
                    this.status({
                        fill: running.length === total ? 'green' : 'yellow',
                        shape: 'dot',
                        text: `${running.length}/${total} running`
                    });
                    this.send({ payload: { running, total } });
                }
            });
        }

        getNodeResources(nodeId) {
            return this.proxy.get(`/nodes/${nodeId}/resources`, (err, data) => {
                if (!err) {
                    this.status({
                        fill: data.load_avg?.[0] < 10 ? 'green' : 'orange',
                        shape: 'dot',
                        text: `${data.load_avg?.[0]?.toFixed(1)} load`
                    });
                    this.send({ payload: data });
                }
            });
        }
    }

    class ProxmoxProxy {
        constructor(url, token) {
            this.url = url;
            this.token = token;
            this.client = new RED.httpIn();
        }

        get(path, callback) {
            this.client.get(`${this.url}${path}`, (err, res) => {
                if (err) {
                    return callback(err);
                }
                res.on('data', callback);
            });
        }

        post(path, data, callback) {
            this.client.post(`${this.url}${path}`, data, (err, res) => {
                if (err) {
                    return callback(err);
                }
                res.on('data', callback);
            });
        }
    }

    RED.nodes.registerType("proxmox-monitor", ProxmoxMonitor);

    return ProxmoxMonitor;
};
