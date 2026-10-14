const API_URL = import.meta.env.VITE_API_URL || "http://localhost:8000/api";

export async function api(path, { token, responseType, ...options } = {}) {
  const storedToken = sessionStorage.getItem("store-token") || token;
  const headers = new Headers(options.headers || {});
  if (options.body && !(options.body instanceof FormData)) {
    headers.set("Content-Type", "application/json");
    options.body = JSON.stringify(options.body);
  }
  const send = (accessToken) => {
    const requestHeaders = new Headers(headers);
    if (accessToken) requestHeaders.set("Authorization", `Bearer ${accessToken}`);
    const url = /^https?:\/\//i.test(path) ? path : `${API_URL}${path}`;
    return fetch(url, { ...options, headers: requestHeaders });
  };
  let response = await send(storedToken);
  if (response.status === 401 && storedToken) {
    const refresh = sessionStorage.getItem("store-refresh");
    if (refresh) {
      const refreshResponse = await fetch(`${API_URL}/auth/token/refresh/`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ refresh }),
      });
      if (refreshResponse.ok) {
        const refreshed = await refreshResponse.json();
        sessionStorage.setItem("store-token", refreshed.access);
        response = await send(refreshed.access);
      } else {
        sessionStorage.removeItem("store-token");
        sessionStorage.removeItem("store-refresh");
      }
    }
  }
  const contentType = response.headers.get("content-type") || "";
  if (responseType === "blob" && response.ok) return response.blob();
  const data = contentType.includes("application/json")
    ? await response.json()
    : null;
  if (!response.ok) {
    const message =
      data?.detail ||
      Object.values(data || {})
        .flat()
        .find((value) => typeof value === "string") ||
      "No se pudo completar la solicitud.";
    throw new Error(message);
  }
  return data;
}
