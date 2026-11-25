
import axios from "axios";

// Create the Axios instance for backend API communication.
const axiosInstance = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL,
  headers: {
    "Content-Type": "application/json",
  },
  timeout: 30000,
});

// Attach the stored JWT to every authenticated API request.
axiosInstance.interceptors.request.use(
  (config) => {
    // Retrieve the JWT from the current browser session.
    const token = sessionStorage.getItem("access_token");

    // Add the Bearer token when the user is authenticated.
    if (token) {
      config.headers.Authorization = `Bearer ${token}`;
    }

    return config;
  },
  (error) => {
    return Promise.reject(error);
  }
);

// Handle successful and failed API responses.
axiosInstance.interceptors.response.use(
  (response) => {
    return response;
  },
  (error) => {
    // Pass API errors to the calling component.
    return Promise.reject(error);
  }
);

export default axiosInstance;
