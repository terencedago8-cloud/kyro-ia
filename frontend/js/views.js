/* ============================================================
   KYRO AI — vues principales
   Chaque vue : async render(container, params)
   ============================================================ */

const Views = {};

/* ---------------- Accueil ---------------- */

Views.home = {
  async render(el) {
    el.innerHTML = `
      <div class="hero">
        <h1>Votre <span class="grad">intelligence artificielle</span><br>tout-en-un</h1>
        <p>Kyro AI réunit chat IA, génération d'images, de vidéos et de code
           dans une seule interface moderne. Chaque demande coûte 3 crédits —
           et vous recevez +200 crédits chaque heure, automatiquement.</p>
        <div class="hero-actions">
          <a class="btn btn-primary" href="${API.token ? "#/chat" : "#/inscription"}">🚀 Commencer</a>
          <a class="btn" href="#/images">🎨 Générer une image</a>
        </div>
      </div>
      <div class="grid grid-2" style="max-width:1000px;margin:0 auto;width:100%">
        <div class="card feature-card">
          <div class="icon">💬</div>
          <h3>Chat IA <span class="price-tag">3 crédits</span></h3>
          <p>Une conversation fluide en français, avec historique complet et conversations multiples.</p>
        </div>
        <div class="card feature-card">
          <div class="icon">🎨</div>
          <h3>Images IA <span class="price-tag">3 crédits</span></h3>
          <p>Transformez vos idées en images haute définition, générées par de vrais modèles d'IA.</p>
        </div>
        <div class="card feature-card">
          <div class="icon">🎬</div>
          <h3>Vidéos IA <span class="price-tag">3 crédits</span></h3>
          <p>Générez des vidéos courtes à partir d'une simple description textuelle.</p>
        </div>
        <div class="card feature-card">
          <div class="icon">💻</div>
          <h3>Code IA <span class="price-tag">3 crédits</span></h3>
          <p>Du code propre et commenté dans toutes les langages, avec explications en français.</p>
        </div>
      </div>
      <div class="card" style="max-width:1000px;margin:24px auto 0;width:100%">
        <div class="card-title">⚡ Système de crédits équitable</div>
        <p class="muted">Chaque utilisateur reçoit <b style="color:var(--blue-electric)">200 crédits par heure</b>,
        automatiquement — même déconnecté. Les crédits non utilisés ne s'accumulent pas :
        le solde est remis à 200 à chaque renouvellement. Les crédits manquants bloquent
        simplement la demande jusqu'au prochain renouvellement.</p>
      </div>`;
  },
};

/* ---------------- Connexion / Inscription ---------------- */

Views.login = {
  async render(el) {
    el.innerHTML = `
      <form class="form card" id="login-form">
        <h2>Connexion</h2>
        <p class="subtitle">Bon retour sur Kyro AI.</p>
        <div class="form-error hidden" id="form-error"></div>
        <div class="field"><label>E-mail</label><input type="email" name="email" required autocomplete="email"></div>
        <div class="field"><label>Mot de passe</label><input type="password" name="password" required autocomplete="current-password"></div>
        <button class="btn btn-primary" style="width:100%" type="submit">Se connecter</button>
        <p class="form-note">Pas encore de compte ? <a href="#/inscription">Créer un compte</a></p>
      </form>`;
    el.querySelector("#login-form").addEventListener("submit", async (e) => {
      e.preventDefault();
      const f = e.target, err = el.querySelector("#form-error");
      err.classList.add("hidden");
      f.querySelector("button").disabled = true;
      try {
        const data = await API.login({ email: f.email.value.trim(), password: f.password.value });
        API.setSession(data.access_token, data.user);
        toast(`Bienvenue, ${data.user.username} !`, "success");
        location.hash = "#/chat";
      } catch (ex) {
        err.textContent = ex.message;
        err.classList.remove("hidden");
      } finally {
        f.querySelector("button").disabled = false;
      }
    });
  },
};

Views.register = {
  async render(el) {
    el.innerHTML = `
      <form class="form card" id="reg-form">
        <h2>Créer un compte</h2>
        <p class="subtitle">Recevez immédiatement vos crédits de bienvenue.</p>
        <div class="form-error hidden" id="form-error"></div>
        <div class="field"><label>Pseudo</label><input name="username" minlength="3" maxlength="64" required pattern="[A-Za-z0-9_.\\-]+"></div>
        <div class="field"><label>E-mail</label><input type="email" name="email" required autocomplete="email"></div>
        <div class="field"><label>Mot de passe (min. 8 caractères)</label><input type="password" name="password" minlength="8" required autocomplete="new-password"></div>
        <div class="field"><label>Confirmer le mot de passe</label><input type="password" name="confirm" minlength="8" required autocomplete="new-password"></div>
        <button class="btn btn-primary" style="width:100%" type="submit">S'inscrire</button>
        <p class="form-note">Déjà inscrit ? <a href="#/connexion">Se connecter</a></p>
      </form>`;
    el.querySelector("#reg-form").addEventListener("submit", async (e) => {
      e.preventDefault();
      const f = e.target, err = el.querySelector("#form-error");
      err.classList.add("hidden");
      if (f.password.value !== f.confirm.value) {
        err.textContent = "Les mots de passe ne correspondent pas.";
        err.classList.remove("hidden");
        return;
      }
      f.querySelector("button").disabled = true;
      try {
        const data = await API.register({ email: f.email.value.trim(), username: f.username.value.trim(), password: f.password.value });
        API.setSession(data.access_token, data.user);
        toast("Compte créé — bienvenue sur Kyro AI !", "success");
        location.hash = "#/chat";
      } catch (ex) {
        err.textContent = ex.message;
        err.classList.remove("hidden");
      } finally {
        f.querySelector("button").disabled = false;
      }
    });
  },
};

/* ---------------- Chat ---------------- */

Views.chat = {
  conversationId: null,
  busy: false,

  async render(el, params) {
    this.conversationId = params.id || null;
    el.innerHTML = `
      <div class="chat-wrap">
        <div class="chat-header">
          <h2 class="section-title" style="margin:0">💬 Chat IA</h2>
          <div style="display:flex;gap:8px">
            <button class="btn btn-sm" id="btn-new-chat">＋ Nouvelle discussion</button>
            <button class="btn btn-sm btn-danger hidden" id="btn-del-conv">🗑 Supprimer</button>
          </div>
        </div>
        <div class="chat-messages" id="chat-messages">
          <div class="empty-state" id="chat-empty">
            <div class="icon">⚡</div>
            <p>Posez votre question à Kyro AI.<br><span class="small">Chaque message coûte 3 crédits.</span></p>
          </div>
        </div>
        <form class="chat-input" id="chat-form">
          <textarea id="chat-text" rows="1" placeholder="Écrivez votre message… (Entrée pour envoyer)" required></textarea>
          <button class="btn btn-primary" type="submit" id="chat-send">Envoyer</button>
        </form>
        <p class="chat-hint">Entrée = envoyer · Maj+Entrée = nouvelle ligne</p>
      </div>`;

    const box = el.querySelector("#chat-messages");
    const ta = el.querySelector("#chat-text");
    const form = el.querySelector("#chat-form");
    const sendBtn = el.querySelector("#chat-send");

    if (this.conversationId) {
      el.querySelector("#btn-del-conv").classList.remove("hidden");
      try {
        const conv = await API.conversation(this.conversationId);
        el.querySelector("#chat-empty")?.remove();
        conv.messages.forEach((m) => this.appendMessage(box, m.role, m.content));
        this.scrollToBottom(box);
      } catch { /* conversation supprimée */ }
    }

    el.querySelector("#btn-new-chat").onclick = () => { Views.chat.conversationId = null; location.hash = "#/chat"; };
    el.querySelector("#btn-del-conv").onclick = async () => {
      if (!confirm("Supprimer cette conversation ?")) return;
      try { await API.deleteConversation(this.conversationId); toast("Conversation supprimée.", "success"); } catch (e) { toast(e.message, "error"); }
      location.hash = "#/chat";
    };

    ta.addEventListener("input", () => { ta.style.height = "auto"; ta.style.height = Math.min(ta.scrollHeight, 160) + "px"; });
    ta.addEventListener("keydown", (e) => {
      if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); form.requestSubmit(); }
    });

    form.addEventListener("submit", async (e) => {
      e.preventDefault();
      if (this.busy) return;
      const message = ta.value.trim();
      if (!message) return;

      this.busy = true;
      sendBtn.disabled = true;
      ta.value = "";
      ta.style.height = "auto";
      el.querySelector("#chat-empty")?.remove();
      this.appendMessage(box, "user", message);
      const typingEl = this.appendTyping(box);
      this.scrollToBottom(box);

      try {
        const res = await API.chat(message, this.conversationId);
        typingEl.remove();
        this.appendMessage(box, "assistant", res.reply);
        this.conversationId = res.conversation_id;
        el.querySelector("#btn-del-conv").classList.remove("hidden");
        if (res.credits) App.updateCredits(res.credits);
        App.loadConversations();
      } catch (ex) {
        typingEl.remove();
        this.appendMessage(box, "assistant", "⚠️ " + ex.message);
        toast(ex.message, ex.status === 402 ? "warning" : "error");
        App.refreshCredits();
      } finally {
        this.busy = false;
        sendBtn.disabled = false;
        ta.focus();
        this.scrollToBottom(box);
      }
    });

    ta.focus();
  },

  appendMessage(box, role, content) {
    const div = document.createElement("div");
    div.className = "msg " + role;
    div.innerHTML = `<div class="avatar">${role === "user" ? "🧑" : "⚡"}</div><div class="bubble">${formatMessage(content)}</div>`;
    box.appendChild(div);
  },

  appendTyping(box) {
    const div = document.createElement("div");
    div.className = "msg assistant";
    div.innerHTML = `<div class="avatar">⚡</div><div class="bubble"><span class="typing"><span></span><span></span><span></span></span></div>`;
    box.appendChild(div);
    return div;
  },

  scrollToBottom(box) { box.scrollTop = box.scrollHeight; },
};

/* ---------------- Générateurs (images / vidéos / code) ---------------- */

function generatorView({ title, subtitle, kind, buttonLabel, costLabel }) {
  return {
    async render(el) {
      el.innerHTML = `
        <div class="gen-panel">
          <h2>${title}</h2>
          <p class="subtitle">${subtitle} — <span class="price-tag">${costLabel}</span></p>
          <form id="gen-form" class="card">
            <div class="gen-row">
              <div class="field">
                <label>Votre demande</label>
                <textarea id="gen-prompt" rows="3" placeholder="Décrivez ce que vous souhaitez…" required></textarea>
              </div>
              <div style="display:flex;align-items:flex-end">
                <button class="btn btn-primary" type="submit" id="gen-btn">${buttonLabel}</button>
              </div>
            </div>
          </form>
          <div class="result-area" id="gen-results"></div>
        </div>`;

      const form = el.querySelector("#gen-form");
      const promptEl = el.querySelector("#gen-prompt");
      const btn = el.querySelector("#gen-btn");
      const results = el.querySelector("#gen-results");

      form.addEventListener("submit", async (e) => {
        e.preventDefault();
        const prompt = promptEl.value.trim();
        if (!prompt) return;
        btn.disabled = true;
        const holder = document.createElement("div");
        holder.innerHTML = `<div class="result-card"><div style="padding:20px;text-align:center"><div class="spinner"></div><p class="muted">Génération en cours…</p></div></div>`;
        results.prepend(holder);

        try {
          let res;
          if (kind === "IMAGE") res = await API.generateImage(prompt);
          else if (kind === "VIDEO") res = await API.generateVideo(prompt);
          else res = await API.generateCode(prompt);

          if (kind === "CODE") {
            holder.innerHTML = `
              <div class="result-card">
                <div class="meta"><span class="prompt">${esc(prompt)}</span>
                <span class="status-pill status-SUCCESS">TERMINÉ</span></div>
                <div class="code-output">${formatMessage(res.text || "")}</div>
              </div>`;
            if (res.credits) App.updateCredits(res.credits);
            App.refreshCredits();
          } else {
            if (res.credits) App.updateCredits(res.credits);
            App.refreshCredits();
            await this.poll(holder, res.generation_id, prompt);
          }
          promptEl.value = "";
        } catch (ex) {
          holder.innerHTML = `<div class="result-card"><div class="meta"><span class="prompt">${esc(prompt)}</span><span class="status-pill status-FAILED">ÉCHEC</span></div><div style="padding:16px;color:var(--danger)">${esc(ex.message)}</div></div>`;
          toast(ex.message, ex.status === 402 ? "warning" : "error");
          App.refreshCredits();
        } finally {
          btn.disabled = false;
        }
      });
    },

    async poll(holder, generationId, prompt) {
      const maxAttempts = 240; // ~4 min max côté client (la tâche continue serveur)
      for (let i = 0; i < maxAttempts; i++) {
        await new Promise((r) => setTimeout(r, 2500));
        let gen;
        try { gen = await API.generation(generationId); } catch { continue; }
        if (gen.status === "SUCCESS") {
          const isVideo = gen.kind === "VIDEO";
          holder.innerHTML = `
            <div class="result-card">
              ${isVideo
                ? `<video src="${esc(gen.media_url)}" controls autoplay muted loop></video>`
                : `<img src="${esc(gen.media_url)}" alt="${esc(gen.prompt)}" loading="lazy">`}
              <div class="meta">
                <span class="prompt">${esc(gen.prompt)}</span>
                <span style="display:flex;gap:8px;align-items:center">
                  <a class="btn btn-sm" href="${esc(gen.media_url)}" download>Télécharger</a>
                  <span class="status-pill status-SUCCESS">TERMINÉ</span>
                </span>
              </div>
            </div>`;
          toast("Génération terminée !", "success");
          return;
        }
        if (gen.status === "FAILED") {
          holder.innerHTML = `<div class="result-card"><div class="meta"><span class="prompt">${esc(prompt)}</span><span class="status-pill status-FAILED">ÉCHEC</span></div><div style="padding:16px;color:var(--danger)">${esc(gen.error || "Erreur inconnue")}<br><span class="small muted">Vos crédits ont été remboursés automatiquement.</span></div></div>`;
          toast("Génération échouée — crédits remboursés.", "error");
          App.refreshCredits();
          return;
        }
        const p = holder.querySelector(".spinner")?.parentElement;
        if (p) p.innerHTML = `<div class="spinner"></div><p class="muted">${gen.status === "PENDING" ? "En attente…" : "Génération en cours…"} (${Math.floor(i * 2.5)}s)</p>`;
      }
      holder.innerHTML = `<div class="result-card"><div style="padding:16px" class="muted">La génération prend plus de temps que prévu. Elle apparaîtra dans votre galerie dès qu'elle sera terminée.</div></div>`;
    },
  };
}

Views.images = generatorView({
  title: "🎨 Générateur d'images",
  subtitle: "Décrivez l'image de vos rêves, l'IA la crée pour vous",
  kind: "IMAGE",
  buttonLabel: "🎨 Générer",
  costLabel: "3 crédits / image",
});

Views.videos = generatorView({
  title: "🎬 Générateur de vidéos",
  subtitle: "Transformez une description en vidéo générée par IA",
  kind: "VIDEO",
  buttonLabel: "🎬 Générer",
  costLabel: "3 crédits / vidéo",
});

Views.code = generatorView({
  title: "💻 Générateur de code",
  subtitle: "Du code propre et commenté, avec explications en français",
  kind: "CODE",
  buttonLabel: "💻 Générer",
  costLabel: "3 crédits / demande",
});

/* ---------------- Historique ---------------- */

Views.history = {
  page: 1,
  kind: "",
  async render(el) {
    el.innerHTML = `
      <div class="page-header"><h2 class="section-title" style="margin:0">🕒 Historique</h2></div>
      <div class="toolbar">
        <select id="h-kind">
          <option value="">Tous les types</option>
          <option value="CHAT">💬 Chat</option>
          <option value="IMAGE">🎨 Images</option>
          <option value="VIDEO">🎬 Vidéos</option>
          <option value="CODE">💻 Code</option>
        </select>
      </div>
      <div id="h-list"><div class="spinner"></div></div>
      <div class="pagination" id="h-pagination"></div>`;

    const load = async () => {
      const list = el.querySelector("#h-list");
      try {
        const data = await API.generations({ kind: this.kind, page: this.page });
        if (!data.items.length) {
          list.innerHTML = `<div class="empty-state"><div class="icon">🕒</div><p>Aucune demande pour l'instant.</p></div>`;
        } else {
          list.innerHTML = `
            <div class="table-wrap"><table>
              <thead><tr><th>Type</th><th>Demande</th><th>Statut</th><th>Crédits</th><th>Date</th></tr></thead>
              <tbody>${data.items.map((g) => `
                <tr>
                  <td>${({ CHAT: "💬 Chat", IMAGE: "🎨 Image", VIDEO: "🎬 Vidéo", CODE: "💻 Code" })[g.kind] || g.kind}</td>
                  <td style="max-width:340px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">${esc(g.prompt)}</td>
                  <td><span class="status-pill status-${g.status}">${g.status}</span></td>
                  <td>${g.credits_cost}</td>
                  <td class="muted">${fmtDate(g.created_at)}</td>
                </tr>`).join("")}</tbody>
            </table></div>`;
        }
        const pages = Math.max(1, Math.ceil(data.total / data.page_size));
        el.querySelector("#h-pagination").innerHTML = pages > 1
          ? `<button class="btn btn-sm" id="h-prev" ${this.page <= 1 ? "disabled" : ""}>← Précédent</button>
             <span class="muted small">Page ${this.page} / ${pages}</span>
             <button class="btn btn-sm" id="h-next" ${this.page >= pages ? "disabled" : ""}>Suivant →</button>`
          : "";
        el.querySelector("#h-prev")?.addEventListener("click", () => { this.page--; load(); });
        el.querySelector("#h-next")?.addEventListener("click", () => { this.page++; load(); });
      } catch (e) {
        list.innerHTML = `<div class="empty-state"><p>${esc(e.message)}</p></div>`;
      }
    };

    el.querySelector("#h-kind").value = this.kind;
    el.querySelector("#h-kind").addEventListener("change", (e) => { this.kind = e.target.value; this.page = 1; load(); });
    load();
  },
};

/* ---------------- Galerie ---------------- */

Views.gallery = {
  page: 1,
  kind: "IMAGE,VIDEO",
  async render(el) {
    el.innerHTML = `
      <div class="page-header"><h2 class="section-title" style="margin:0">🖼️ Ma galerie</h2></div>
      <div class="toolbar">
        <select id="g-kind">
          <option value="IMAGE,VIDEO">Tout</option>
          <option value="IMAGE">🎨 Images</option>
          <option value="VIDEO">🎬 Vidéos</option>
        </select>
      </div>
      <div id="g-list"><div class="spinner"></div></div>
      <div class="pagination" id="g-pagination"></div>`;

    const load = async () => {
      const list = el.querySelector("#g-list");
      try {
        const data = await API.gallery(this.page, this.kind);
        if (!data.items.length) {
          list.innerHTML = `<div class="empty-state"><div class="icon">🖼️</div><p>Aucune image ni vidéo générée pour l'instant.</p></div>`;
        } else {
          list.innerHTML = `<div class="gallery-grid">${data.items.map((g) => `
            <div class="gallery-item" data-url="${esc(g.media_url)}" data-kind="${g.kind}">
              ${g.kind === "VIDEO"
                ? `<video src="${esc(g.media_url)}" muted preload="metadata"></video>`
                : `<img src="${esc(g.media_url)}" alt="${esc(g.prompt)}" loading="lazy">`}
              <span class="badge">${g.kind === "VIDEO" ? "🎬" : "🎨"}</span>
            </div>`).join("")}</div>`;
          list.querySelectorAll(".gallery-item").forEach((item) => {
            item.addEventListener("click", () => {
              const url = item.dataset.url;
              const lb = document.createElement("div");
              lb.className = "lightbox";
              lb.innerHTML = `<span class="close">×</span>${item.dataset.kind === "VIDEO" ? `<video src="${url}" controls autoplay></video>` : `<img src="${url}" alt="">`}`;
              lb.addEventListener("click", (e) => { if (e.target === lb || e.target.classList.contains("close")) lb.remove(); });
              document.body.appendChild(lb);
            });
          });
        }
        const pages = Math.max(1, Math.ceil(data.total / data.page_size));
        el.querySelector("#g-pagination").innerHTML = pages > 1
          ? `<button class="btn btn-sm" id="g-prev" ${this.page <= 1 ? "disabled" : ""}>← Précédent</button>
             <span class="muted small">Page ${this.page} / ${pages}</span>
             <button class="btn btn-sm" id="g-next" ${this.page >= pages ? "disabled" : ""}>Suivant →</button>`
          : "";
        el.querySelector("#g-prev")?.addEventListener("click", () => { this.page--; load(); });
        el.querySelector("#g-next")?.addEventListener("click", () => { this.page++; load(); });
      } catch (e) {
        list.innerHTML = `<div class="empty-state"><p>${esc(e.message)}</p></div>`;
      }
    };
    el.querySelector("#g-kind").value = this.kind;
    el.querySelector("#g-kind").addEventListener("change", (e) => { this.kind = e.target.value; this.page = 1; load(); });
    load();
  },
};

/* ---------------- Profil & crédits ---------------- */

Views.profile = {
  async render(el) {
    el.innerHTML = `<div class="spinner"></div>`;
    let data;
    try { data = await API.me(); } catch (e) { el.innerHTML = `<div class="empty-state"><p>${esc(e.message)}</p></div>`; return; }
    const u = data.user, c = data.credits;

    el.innerHTML = `
      <div class="page-header"><h2 class="section-title" style="margin:0">👤 Profil & crédits</h2></div>
      <div class="grid grid-2">
        <div class="card">
          <div class="card-title">Compte</div>
          <p><b>Pseudo :</b> ${esc(u.username)}</p>
          <p class="muted"><b>E-mail :</b> ${esc(u.email)}</p>
          <p class="muted"><b>Rôle :</b> ${esc(u.role)}</p>
          <p class="muted"><b>Inscrit le :</b> ${fmtDate(u.created_at)}</p>
          <p class="muted"><b>Générations :</b> ${data.stats.generations} (${data.stats.successes} réussies)</p>
        </div>
        <div class="card">
          <div class="card-title">⚡ Portefeuille de crédits</div>
          <p style="font-size:2.4rem;font-weight:800" class="grad-text"><span id="p-balance">${c.balance}</span> <span class="muted" style="font-size:1rem">crédits</span></p>
          <p class="muted">Prochain renouvellement : <b id="p-countdown">${mmss(c.seconds_until_renewal)}</b></p>
          <p class="muted small">Chaque heure, votre solde est automatiquement remis à <b>${c.hourly_grant} crédits</b>
          (les crédits non utilisés ne s'accumulent pas). Chaque demande de chat, image, vidéo ou code coûte 3 crédits.</p>
        </div>
      </div>

      <div class="card" style="margin-top:16px">
        <div class="card-title">Modifier le compte</div>
        <form id="profile-form">
          <div class="grid grid-2">
            <div class="field"><label>Pseudo</label><input name="username" value="${esc(u.username)}" minlength="3" maxlength="64"></div>
            <div></div>
            <div class="field"><label>Mot de passe actuel (requis pour changer)</label><input type="password" name="current_password" autocomplete="current-password"></div>
            <div class="field"><label>Nouveau mot de passe</label><input type="password" name="new_password" autocomplete="new-password"></div>
          </div>
          <button class="btn btn-primary" type="submit">Enregistrer</button>
        </form>
      </div>

      <div class="card" style="margin-top:16px">
        <div class="card-title">Historique des crédits</div>
        <div id="p-history"><div class="spinner"></div></div>
      </div>`;

    // Compte à rebours local
    let seconds = c.seconds_until_renewal;
    clearInterval(App.profileTimer);
    App.profileTimer = setInterval(() => {
      seconds = Math.max(0, seconds - 1);
      const cd = document.getElementById("p-countdown");
      if (!cd) return clearInterval(App.profileTimer);
      cd.textContent = mmss(seconds);
      if (seconds === 0) { App.refreshCredits(); seconds = 60 * 60; }
    }, 1000);

    el.querySelector("#profile-form").addEventListener("submit", async (e) => {
      e.preventDefault();
      const f = e.target;
      const payload = { username: f.username.value.trim() };
      if (f.new_password.value) {
        payload.current_password = f.current_password.value;
        payload.new_password = f.new_password.value;
      }
      try {
        const res = await API.updateProfile(payload);
        const sess = API.user;
        API.setSession(API.token, { ...sess, username: res.user.username });
        toast("Profil mis à jour.", "success");
      } catch (ex) { toast(ex.message, "error"); }
    });

    // Historique de crédits
    try {
      const h = await API.creditsHistory();
      const box = el.querySelector("#p-history");
      if (!h.items.length) { box.innerHTML = `<p class="muted">Aucun mouvement.</p>`; }
      else {
        box.innerHTML = `
          <div class="table-wrap"><table>
            <thead><tr><th>Mouvement</th><th>Delta</th><th>Solde après</th><th>Raison</th><th>Date</th></tr></thead>
            <tbody>${h.items.map((r) => `
              <tr>
                <td>${esc(r.kind)}</td>
                <td class="${r.delta >= 0 ? "delta-pos" : "delta-neg"}">${r.delta >= 0 ? "+" : ""}${r.delta}</td>
                <td>${r.balance_after}</td>
                <td class="muted">${esc(r.reason)}</td>
                <td class="muted">${fmtDate(r.created_at)}</td>
              </tr>`).join("")}</tbody>
          </table></div>`;
      }
    } catch { /* rien */ }
  },
};
