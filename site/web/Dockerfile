# Local web container (infra/docker-compose.yml service `web`): the site with the live Ask page.
# Built with NEXT_PUBLIC_BT_LOCAL=1, so it carries the live Ask code the public build leaves out.
# Published on 127.0.0.1 only; never deployed. The public site is a plain `npm run build` on Vercel.
FROM node:24.14.0-slim
WORKDIR /app
ENV NEXT_TELEMETRY_DISABLED=1 NEXT_PUBLIC_BT_LOCAL=1
COPY package.json package-lock.json ./
RUN npm ci
COPY . .
RUN npm run build && chown -R node:node /app/.next
# The history volume (asked questions, real names) must be writable by the node user.
RUN mkdir -p /var/lib/blind-tuner-web && chown node:node /var/lib/blind-tuner-web
USER node
EXPOSE 3000
CMD ["node_modules/.bin/next", "start", "-H", "0.0.0.0", "-p", "3000"]
