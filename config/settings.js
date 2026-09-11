# Smart Home Dashboard - Node-RED Configuration

node_red:
  http:
    port: 1880
    admin: admin
  user: admin
  password: admin
  httpAdminRoot: node-red
  httpStatic: /usr/share/node-red
  httpStaticCdn: https://unpkg.com
  httpStaticLegacy: https://node-js-legacy.cdn.npmjs.com/node-red
  httpNode: true
  httpNodeAdminAuth: admin
  httpNodeCors:
    origin: "*"
    credentials: false
  httpStaticAuth: false
  httpStaticAuthUser: admin
  httpStaticAuthPass: admin
  ui:
    theme: complete
    tabs:
      - file: flows/dashboard-configuration.js
        name: Dashboard
    order:
      - Dashboard
  server:
    xheaders: false
    xforwarded: false
    ssl:
      enabled: false
      cert: /etc/ssl/certs/node-red.crt
      key: /etc/ssl/private/node-red.key
  logging:
    console:
      level: info
    file:
      level: info
      maxFiles: 10
      maxSize: 10485760
  plugins:
    - dashboard
    - node-red-node-hubitat
    - node-red-node-unifi
    - node-red-contrib-kanbanflow
