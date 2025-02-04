FROM node:21

WORKDIR /app

COPY alarm.js .
COPY package.json .

RUN mkdir img

RUN npm install

CMD ["node", "alarm.js"]