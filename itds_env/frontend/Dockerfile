# Step 1: Build the React application
FROM node:18-alpine AS build

WORKDIR /app

# Copy package configuration files
COPY package*.json ./

# Install frontend dependencies
RUN npm ci

# Copy frontend source files
COPY . .

# Build the React application with relative API URL paths
ENV REACT_APP_API_URL=""
RUN npm run build

# Step 2: Serve the React application with Nginx in production
FROM nginx:1.25-alpine

# Copy built static assets from Step 1
COPY --from=build /app/build /usr/share/nginx/html

# Copy custom Nginx routing and proxy configuration
COPY nginx.conf /etc/nginx/conf.d/default.conf

EXPOSE 80

CMD ["nginx", "-g", "daemon off;"]
