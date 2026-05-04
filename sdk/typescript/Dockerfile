FROM node:20-slim AS deps
WORKDIR /sdk
COPY package.json ./
RUN npm install

FROM deps AS test
COPY tsconfig.json jest.config.js ./
COPY src/ ./src/
COPY tests/ ./tests/
CMD ["npm", "test"]
