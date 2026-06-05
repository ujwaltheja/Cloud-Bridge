FROM node:22-alpine

WORKDIR /app

COPY --chown=node:node package*.json ./
RUN npm install

COPY --chown=node:node . .

USER node

EXPOSE 5173

CMD ["npm", "run", "dev"]
