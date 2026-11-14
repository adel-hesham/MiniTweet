export interface User {
  id: number;
  username: string;
  created_at?: string;
}

export interface Tweet {
  id: number;
  user_id: number;
  username: string;
  content: string;
  created_at: string;
}

export interface LikeInfo {
  count: number;
  liked_by_me: boolean;
}

export interface LikeResult {
  tweet_id: number;
  liked: boolean;
  count: number;
}

export interface AppNotification {
  id: number;
  type: string;
  message: string;
  tweet_id: number | null;
  is_read: boolean;
  created_at: string;
}

export interface NotificationList {
  unread: number;
  notifications: AppNotification[];
}

export class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

const TOKEN_KEY = "minitweet_token";
export const getToken = (): string | null => localStorage.getItem(TOKEN_KEY);
export const setToken = (token: string): void => localStorage.setItem(TOKEN_KEY, token);
export const clearToken = (): void => localStorage.removeItem(TOKEN_KEY);

function errorText(data: any): string {
  const detail = data?.detail;
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail) && detail.length > 0 && detail[0]?.msg) return String(detail[0].msg);
  return "Something went wrong";
}

async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const headers = new Headers(options.headers);
  headers.set("Content-Type", "application/json");
  const token = getToken();
  if (token) headers.set("Authorization", `Bearer ${token}`);

  let response: Response;
  try {
    response = await fetch(`/api${path}`, { ...options, headers });
  } catch {
    throw new ApiError(0, "Cannot reach the server");
  }
  const data = await response.json().catch(() => ({}));
  if (!response.ok) throw new ApiError(response.status, errorText(data));
  return data as T;
}

// ---- users ----
export function register(username: string, password: string): Promise<User> {
  return request<User>("/users/register", {
    method: "POST",
    body: JSON.stringify({ username, password }),
  });
}

export function login(username: string, password: string): Promise<{ access_token: string }> {
  return request<{ access_token: string }>("/users/login", {
    method: "POST",
    body: JSON.stringify({ username, password }),
  });
}

export function me(): Promise<User> {
  return request<User>("/users/me");
}

// ---- tweets ----
export function listTweets(): Promise<Tweet[]> {
  return request<Tweet[]>("/tweets?limit=30");
}

export function createTweet(content: string): Promise<Tweet> {
  return request<Tweet>("/tweets", { method: "POST", body: JSON.stringify({ content }) });
}

export async function deleteTweet(id: number): Promise<void> {
  await request<unknown>(`/tweets/${id}`, { method: "DELETE" });
}

// ---- likes ----
export function getLikes(ids: number[]): Promise<Record<string, LikeInfo>> {
  return request<Record<string, LikeInfo>>(`/likes?tweet_ids=${ids.join(",")}`);
}

export function likeTweet(id: number): Promise<LikeResult> {
  return request<LikeResult>("/likes", { method: "POST", body: JSON.stringify({ tweet_id: id }) });
}

export function unlikeTweet(id: number): Promise<LikeResult> {
  return request<LikeResult>(`/likes/${id}`, { method: "DELETE" });
}

// ---- notifications ----
export function getNotifications(): Promise<NotificationList> {
  return request<NotificationList>("/notifications");
}

export function markNotificationsRead(): Promise<{ unread: number }> {
  return request<{ unread: number }>("/notifications/read", { method: "POST" });
}

// Reads the claims inside a JWT (no verification, just for showing them on screen).
export function decodeToken(token: string): Record<string, unknown> | null {
  try {
    const payload = token.split(".")[1].replace(/-/g, "+").replace(/_/g, "/");
    return JSON.parse(atob(payload));
  } catch {
    return null;
  }
}
