FROM node:20-alpine

WORKDIR /app

# Copy package files
COPY package*.json ./

# Install dependencies
RUN npm install

# Copy application code
COPY . .

# Build args for production
ARG BUILD_ENV=development
ARG NEXT_PUBLIC_API_URL=http://localhost:8000

# Set env so Next.js bakes it into the build
ENV NEXT_PUBLIC_API_URL=$NEXT_PUBLIC_API_URL

# Build for production (used when command is 'npm start')
RUN if [ "$BUILD_ENV" = "production" ]; then npm run build; fi

# Expose port
EXPOSE 3000

# Run the application (overridden by docker-compose in production)
CMD ["npm", "run", "dev"]
