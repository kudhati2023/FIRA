FROM node:20-alpine

WORKDIR /app

# Copy dependency files
COPY package*.json /app/

# Install dependencies
RUN npm install

# Copy source files
COPY . /app/

EXPOSE 3000

# Start Vite dev server with hot reload
CMD ["npm", "run", "dev"]
