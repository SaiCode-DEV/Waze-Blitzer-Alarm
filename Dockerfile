FROM node:21-alpine

WORKDIR /app

COPY alarm.js .
COPY package.json .
COPY stack.env .

# Create data and img directories
RUN mkdir -p img data

RUN npm install

CMD ["npm", "run", "portainer"]