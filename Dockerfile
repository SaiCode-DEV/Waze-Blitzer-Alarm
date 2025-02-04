FROM node:21

WORKDIR /app

COPY alarm.js .
COPY package.json .
COPY stack.env .

RUN mkdir img

RUN npm install

CMD ["npm", "portainer"]