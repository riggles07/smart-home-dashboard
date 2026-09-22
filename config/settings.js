# Smart Home Dashboard - Node-RED Configuration

node_red:
  http:
    port: 1880
    admin: admin
  user: admin
  # Credentials resolved from .env via credential rotation - never hardcoded
  password: ${NODE_RED_PASS}
  httpAdminRoot: node-red
  httpStatic: /usr/share/node-red
  httpNode: true
  httpNodeAdminAuth: admin
  httpNodeCors:
    origin: "*"
    credentials: false
  httpStaticAuth: true
  httpStaticAuthUser: ${NODE_RED_USER}
  httpStaticAuthPass: ${NODE_RED_PASS}
  ui:
    theme: complete
    css: css/dashboard.css
    tabs:
      - file: flows/dashboard-configuration.js
        name: Dashboard
    order:
      - Dashboard
  server:
    xheaders: false
    xforwarded: false
    ssl:
      enabled: true
      cert: /etc/node-red/fullchain.pem
      key: /etc/node-red/private.key
      port: 1881
  httpStaticHeaders:
    X-Frame-Options: DENY
    X-Content-Type-Options: nosniff
    X-XSS-Protection: "1; mode=block"
    Strict-Transport-Security: "max-age=31536000; includeSubDomains"
    Content-Security-Policy: "default-src 'self'; script-src 'self' 'unsafe-inline' 'unsafe-eval'; style-src 'self' 'unsafe-inline'; img-src 'self' data: https:; font-src 'self' data:;"
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
