import axios from "axios";

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL;
export const API = `${BACKEND_URL}/api`;

export const api = axios.create({
  baseURL: API,
  withCredentials: true,
});

// Auth endpoints legitimately 401 as part of their normal flow (checking
// whether a visitor is logged in, a stale/invalid OAuth callback) and already
// handle that locally wherever they're called -- don't double-handle those.
// Every OTHER 401 means a session that was valid went stale mid-visit; without
// this, the page just keeps rendering as if still authenticated while every
// subsequent action silently fails. Hard redirect (not a router navigate) so
// AuthContext/React Query state resets cleanly instead of leaving stale
// "logged in" UI mixed with failed requests.
api.interceptors.response.use(
  (res) => res,
  (error) => {
    const url = error.config?.url || "";
    if (error.response?.status === 401 && !url.includes("/auth/") && window.location.pathname !== "/") {
      window.location.href = "/?session_expired=1";
    }
    return Promise.reject(error);
  }
);

export const fileUrl = (path) => `${API}/files/${path}`;
