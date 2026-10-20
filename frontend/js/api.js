/* ============================================================
   KYRO AI — client API (jeton, requêtes, helpers)
   ============================================================ */

const API = {
  get token() { return localStorage.getItem("kyro_token"); },
  get user() {
    try { return JSON.parse(localStorage.getItem("kyro_user")); } catch { return null; }
  },

  setSession(token, user) {
    localStorage.setItem("kyro_token", token);
    localStorage.setItem("kyro_user", JSON.stringify(user));
    document.dispatchEvent(new Event("kyro:session"));
  },

  clearSession() {
    localStorage.removeItem("kyro_token");
    localStorage.removeItem("kyro_user");
    document.dispatchEvent(new Event("kyro:session"));
  },

  get isAdmin() { const u = this.user; return !!u && u.role === "ADMIN"; },

  async req(path, { method = "GET", body } = {}) {
    const headers = { "Content-Type": "application/json" };
    if (this.token) headers.Authorization = "Bearer " + this.token;
    let res;
    try {
      res = await fetch(path, { method, headers, body: body !== undefined ? JSON.stringify(body) : undefined });
    } catch {
      throw new Error("Impossible de joindre le serveur. Vérifiez votre connexion.");
    }
    if (res.status === 204) return null;
    let data = null;
    try { data = await res.json(); } catch { /* pas de corps JSON */ }
    if (!res.ok) {
      if (res.status === 401 && this.token) {
        this.clearSession();
        if (!location.hash.startsWith("#/connexion")) location.hash = "#/connexion";
      }
      let msg = "Erreur " + res.status;
      const d = data && data.detail;
      if (typeof d === "string") msg = d;
      else if (Array.isArray(d) && d[0]) msg = d.map((e) => e.msg).join(" — ");
      else if (typeof d === "object" && d) msg = Object.entries(d).map(([k, v]) => `${k} : ${v}`).join(" — ");
      else if (data && data.message) msg = data.message;
      const err = new Error(msg);
      err.status = res.status;
      throw err;
    }
    return data;
  },

  // --- Auth ---
  register(payload) { return this.req("/api/auth/register", { method: "POST", body: payload }); },
  login(payload) { return this.req("/api/auth/login", { method: "POST", body: payload }); },

  // --- Profil / crédits ---
  me() { return this.req("/api/me"); },
  updateProfile(payload) { return this.req("/api/me", { method: "PATCH", body: payload }); },
  creditsHistory(page = 1) { return this.req(`/api/me/credits/history?page=${page}`); },

  // --- Chat ---
  chat(message, conversationId) {
    return this.req("/api/chat", { method: "POST", body: { message, conversation_id: conversationId } });
  },
  conversations() { return this.req("/api/conversations"); },
  conversation(id) { return this.req(`/api/conversations/${id}`); },
  deleteConversation(id) { return this.req(`/api/conversations/${id}`, { method: "DELETE" }); },

  // --- Générations ---
  generateImage(prompt) { return this.req("/api/images", { method: "POST", body: { prompt } }); },
  generateVideo(prompt) { return this.req("/api/videos", { method: "POST", body: { prompt } }); },
  generateCode(prompt) { return this.req("/api/code", { method: "POST", body: { prompt } }); },
  generation(id) { return this.req(`/api/generations/${id}`); },
  generations({ kind, page = 1 } = {}) {
    const q = new URLSearchParams({ page });
    if (kind) q.set("kind", kind);
    return this.req(`/api/generations?${q}`);
  },
  gallery(page = 1, kind = "IMAGE,VIDEO") { return this.req(`/api/gallery?page=${page}&kind=${kind}`); },

  // --- Admin ---
  adminStats() { return this.req("/api/admin/stats"); },
  adminUsers(search = "", page = 1) { return this.req(`/api/admin/users?search=${encodeURIComponent(search)}&page=${page}`); },
  adminUser(id) { return this.req(`/api/admin/users/${id}`); },
  adminPatchUser(id, payload) { return this.req(`/api/admin/users/${id}`, { method: "PATCH", body: payload }); },
  adminDeleteUser(id) { return this.req(`/api/admin/users/${id}`, { method: "DELETE" }); },
  adminCredits(id, payload) { return this.req(`/api/admin/users/${id}/credits`, { method: "POST", body: payload }); },
  adminCreditsHistory(id, page = 1) { return this.req(`/api/admin/users/${id}/credits/history?page=${page}`); },
  adminGrantAll(payload) { return this.req("/api/admin/credits/all", { method: "POST", body: payload }); },
  adminSettings() { return this.req("/api/admin/settings"); },
  adminSaveSettings(settings) { return this.req("/api/admin/settings", { method: "PUT", body: { settings } }); },
  adminLogs() { return this.req("/api/admin/logs"); },
  adminGenerations(params = {}) {
    const q = new URLSearchParams(params);
    return this.req(`/api/admin/generations?${q}`);
  },
};

/* ---------- Helpers UI ---------- */

function esc(s) {
  return String(s ?? "").replace(/[&<>"']/g, (c) =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}

/** Rendu léger du texte : blocs ```code``` et `inline code` (contenu déjà échappé). */
function formatMessage(text) {
  let out = esc(text);
  out = out.replace(/```(\w*)\n?([\s\S]*?)```/g, (_, lang, code) => `<pre><code>${code}</code></pre>`);
  out = out.replace(/`([^`\n]+)`/g, "<code>$1</code>");
  return out;
}

function toast(message, type = "info", ms = 4500) {
  const box = document.getElementById("toasts");
  const el = document.createElement("div");
  el.className = "toast " + type;
  el.textContent = message;
  box.appendChild(el);
  setTimeout(() => { el.style.opacity = "0"; el.style.transition = "opacity .4s"; setTimeout(() => el.remove(), 400); }, ms);
}

function timeAgo(iso) {
  if (!iso) return "—";
  const s = (Date.now() - new Date(iso).getTime()) / 1000;
  if (s < 60) return "à l'instant";
  if (s < 3600) return `il y a ${Math.floor(s / 60)} min`;
  if (s < 86400) return `il y a ${Math.floor(s / 3600)} h`;
  return new Date(iso).toLocaleDateString("fr-FR");
}

function fmtDate(iso) {
  if (!iso) return "—";
  return new Date(iso).toLocaleString("fr-FR", { dateStyle: "short", timeStyle: "short" });
}

function mmss(seconds) {
  const m = Math.floor(seconds / 60), s = seconds % 60;
  return `${String(m).padStart(2, "0")}:${String(s).padStart(2, "0")}`;
}

function debounce(fn, ms = 350) {
  let t;
  return (...args) => { clearTimeout(t); t = setTimeout(() => fn(...args), ms); };
}
