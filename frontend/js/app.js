/* ============================================================
   KYRO AI — application : routeur, barre supérieure, crédits
   ============================================================ */

const App = {
  profileTimer: null,
  creditsTimer: null,
  secondsUntilRenewal: null,

  routes: [
    { path: "", view: Views.home, auth: false },
    { path: "connexion", view: Views.login, auth: false, guestOnly: true },
    { path: "inscription", view: Views.register, auth: false, guestOnly: true },
    { path: "chat", view: Views.chat, auth: true },
    { path: "chat/:id", view: Views.chat, auth: true },
    { path: "images", view: Views.images, auth: true },
    { path: "videos", view: Views.videos, auth: true },
    { path: "code", view: Views.code, auth: true },
    { path: "historique", view: Views.history, auth: true },
    { path: "galerie", view: Views.gallery, auth: true },
    { path: "profil", view: Views.profile, auth: true },
    { path: "admin", view: AdminViews.dashboard, admin: true },
    { path: "admin/utilisateurs", view: AdminViews.users, admin: true },
    { path: "admin/credits", view: AdminViews.credits, admin: true },
    { path: "admin/parametres", view: AdminViews.settings, admin: true },
    { path: "admin/journaux", view: AdminViews.logs, admin: true },
  ],

  /* ---------- Routeur ---------- */

  async route() {
    const cleanPath = location.hash.replace(/^#\/?/, "");
    const segs = cleanPath ? cleanPath.split("/") : [""];

    // Le chemin est comparé ENTIÈREMENT segment par segment (avec extraction
    // des paramètres :id). Comparer seulement le premier segment faisait tomber
    // /admin/utilisateurs, /admin/credits, /admin/parametres et /admin/journaux
    // sur le tableau de bord — les onglets de l'admin étaient donc morts.
    let route = null;
    const params = {};
    for (const r of this.routes) {
      const rs = r.path.split("/");
      if (rs.length !== segs.length) continue;
      const found = {};
      const ok = rs.every((seg, i) => {
        if (seg.startsWith(":")) { found[seg.slice(1)] = segs[i]; return true; }
        return seg === segs[i];
      });
      if (ok) { route = r; Object.assign(params, found); break; }
    }

    const view = document.getElementById("view");

    if (route && route.auth && !API.token) {
      toast("Connectez-vous pour accéder à cette page.", "warning");
      location.hash = "#/connexion";
      return;
    }
    if (route && route.admin && !API.isAdmin) {
      if (!API.token) { location.hash = "#/connexion"; return; }
      view.innerHTML = `<div class="empty-state"><div class="icon">🔒</div><p>Accès réservé aux administrateurs.</p></div>`;
      return;
    }
    if (route && route.guestOnly && API.token) {
      location.hash = "#/chat";
      return;
    }

    clearInterval(this.profileTimer);
    this.setActiveNav(cleanPath);
    this.closeSidebar();

    view.innerHTML = `<div class="loading">Chargement…</div>`;
    try {
      await (route || this.routes[0]).view.render(view, params);
    } catch (e) {
      view.innerHTML = `<div class="empty-state"><div class="icon">⚠️</div><p>${esc(e.message || "Erreur de rendu.")}</p></div>`;
    }
  },

  /* ---------- Barre supérieure ---------- */

  renderUserArea() {
    const area = document.getElementById("user-area");
    const badge = document.getElementById("credits-badge");
    const user = API.user;

    document.querySelectorAll(".auth-only").forEach((e) => e.classList.toggle("hidden", !user));
    document.querySelectorAll(".admin-only").forEach((e) => e.classList.toggle("hidden", !API.isAdmin));

    if (user) {
      badge.classList.remove("hidden");
      area.innerHTML = `
        <div class="user-chip" id="user-chip" title="Profil et crédits">
          <div class="avatar">${esc((user.username || "?")[0].toUpperCase())}</div>
          <span class="small">${esc(user.username)}</span>
        </div>
        <button class="btn btn-sm btn-ghost" id="btn-logout" title="Se déconnecter">⏻</button>`;
      document.getElementById("user-chip").addEventListener("click", () => { location.hash = "#/profil"; });
      document.getElementById("btn-logout").addEventListener("click", () => {
        API.clearSession();
        toast("Vous êtes déconnecté.", "success");
        location.hash = "#/";
      });
      this.refreshCredits();
      this.loadConversations();
    } else {
      badge.classList.add("hidden");
      area.innerHTML = `
        <a class="btn btn-primary" href="#/connexion">Connexion</a>
        <a class="btn btn-ghost" href="#/inscription">Inscription</a>`;
      clearInterval(this.creditsTimer);
    }
  },

  /* ---------- Solde de crédits + compte à rebours ---------- */

  async refreshCredits() {
    if (!API.token) return;
    try {
      const data = await API.me();
      this.updateCredits(data.credits);
    } catch { /* token invalide géré par API.req */ }
  },

  updateCredits(credits) {
    const val = document.getElementById("credits-value");
    const timer = document.getElementById("credits-timer");
    if (!val || !credits) return;
    val.textContent = credits.balance;
    document.getElementById("credits-badge").title =
      `${credits.balance} crédits disponibles — +${credits.hourly_grant} crédits dans ${mmss(credits.seconds_until_renewal)}`;

    this.secondsUntilRenewal = credits.seconds_until_renewal;
    clearInterval(this.creditsTimer);
    const tick = () => {
      const t = document.getElementById("credits-timer");
      if (!t) return clearInterval(this.creditsTimer);
      if (this.secondsUntilRenewal <= 0) {
        t.textContent = "renouvellement…";
        this.refreshCredits();
        this.secondsUntilRenewal = 3600;
        return;
      }
      t.textContent = `⏳ ${mmss(this.secondsUntilRenewal)}`;
      this.secondsUntilRenewal--;
    };
    tick();
    this.creditsTimer = setInterval(tick, 1000);
  },

  /* ---------- Conversations (barre latérale) ---------- */

  async loadConversations() {
    const box = document.getElementById("conv-list");
    if (!box || !API.token) return;
    try {
      const convs = await API.conversations();
      box.innerHTML = convs.length
        ? convs.map((c) => `<a href="#/chat/${c.id}" title="${esc(c.title)}" ${location.hash === `#/chat/${c.id}` ? 'class="active"' : ""}>${esc(c.title)}</a>`).join("")
        : `<em class="muted small" style="padding:0 12px">Aucune conversation</em>`;
    } catch { /* silencieux */ }
  },

  /* ---------- Navigation active ---------- */

  setActiveNav(path) {
    document.querySelectorAll("[data-nav]").forEach((a) => {
      const nav = a.dataset.nav;
      const active = path === nav || (nav !== "" && path.startsWith(nav));
      a.classList.toggle("active", active);
    });
  },

  /* ---------- Sidebar mobile ---------- */

  closeSidebar() {
    document.getElementById("sidebar").classList.remove("open");
    document.getElementById("sidebar-overlay").classList.remove("show");
  },

  /* ---------- Démarrage ---------- */

  init() {
    document.getElementById("btn-menu").addEventListener("click", () => {
      document.getElementById("sidebar").classList.toggle("open");
      document.getElementById("sidebar-overlay").classList.toggle("show");
    });
    document.getElementById("sidebar-overlay").addEventListener("click", () => this.closeSidebar());

    document.addEventListener("kyro:session", () => this.renderUserArea());
    window.addEventListener("hashchange", () => { this.route(); this.loadConversations(); });

    // Rafraîchit le solde toutes les 30 s (le renouvellement reste calculé côté serveur)
    setInterval(() => { if (API.token) this.refreshCredits(); }, 30000);

    this.renderUserArea();
    this.route();
  },
};

document.addEventListener("DOMContentLoaded", () => App.init());
