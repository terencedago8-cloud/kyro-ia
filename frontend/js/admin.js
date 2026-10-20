/* ============================================================
   KYRO AI — vues d'administration (réservées au rôle ADMIN)
   ============================================================ */

const AdminViews = {};

function adminTabs(active) {
  const tabs = [
    ["#/admin", "📊 Tableau de bord"],
    ["#/admin/utilisateurs", "👥 Utilisateurs"],
    ["#/admin/credits", "💰 Crédits"],
    ["#/admin/parametres", "⚙️ Paramètres"],
    ["#/admin/journaux", "📜 Journaux"],
  ];
  return `<div class="admin-tabs">${tabs.map(([href, label]) =>
    `<a href="${href}" class="${active === href ? "active" : ""}">${label}</a>`).join("")}</div>`;
}

/* ---------------- Tableau de bord ---------------- */

AdminViews.dashboard = {
  async render(el) {
    el.innerHTML = adminTabs("#/admin") + `<div class="spinner"></div>`;
    try {
      const s = await AdminViews.dashboard._stats();
      el.innerHTML = adminTabs("#/admin") + `
        <h2 class="section-title">📊 Statistiques</h2>
        <div class="grid grid-4">
          <div class="card stat-card"><div class="value">${s.total_users}</div><div class="label">Utilisateurs inscrits</div></div>
          <div class="card stat-card"><div class="value">${s.active_users_24h}</div><div class="label">Actifs (24 h)</div></div>
          <div class="card stat-card"><div class="value">${s.chat_requests}</div><div class="label">Demandes chat IA</div></div>
          <div class="card stat-card"><div class="value">${s.images}</div><div class="label">Images générées</div></div>
          <div class="card stat-card"><div class="value">${s.videos}</div><div class="label">Vidéos générées</div></div>
          <div class="card stat-card"><div class="value">${s.code_requests}</div><div class="label">Demandes de code</div></div>
          <div class="card stat-card"><div class="value">${s.credits_consumed_total}</div><div class="label">Crédits consommés (total)</div></div>
          <div class="card stat-card"><div class="value">${s.failed_generations}</div><div class="label">Générations échouées</div></div>
        </div>
        <div class="card" style="margin-top:16px">
          <div class="card-title">Dernières générations</div>
          <div id="admin-recent"><div class="spinner"></div></div>
        </div>`;
      const recent = await API.adminGenerations({ page_size: 10 });
      el.querySelector("#admin-recent").innerHTML = recent.items.length
        ? `<div class="table-wrap"><table>
            <thead><tr><th>Type</th><th>Demande</th><th>Statut</th><th>Date</th></tr></thead>
            <tbody>${recent.items.map((g) => `
              <tr><td>${g.kind}</td>
              <td style="max-width:300px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">${esc(g.prompt)}</td>
              <td><span class="status-pill status-${g.status}">${g.status}</span></td>
              <td class="muted">${fmtDate(g.created_at)}</td></tr>`).join("")}</tbody></table></div>`
        : `<p class="muted">Aucune génération.</p>`;
    } catch (e) {
      el.innerHTML = adminTabs("#/admin") + `<div class="empty-state"><p>${esc(e.message)}</p></div>`;
    }
  },
  async _stats() { return API.adminStats(); },
};

/* ---------------- Utilisateurs ---------------- */

AdminViews.users = {
  search: "",
  page: 1,
  async render(el) {
    el.innerHTML = adminTabs("#/admin/utilisateurs") + `
      <h2 class="section-title">👥 Gestion des utilisateurs</h2>
      <div class="toolbar">
        <input id="u-search" placeholder="Rechercher par pseudo ou e-mail…" value="${esc(this.search)}">
        <button class="btn btn-sm" id="u-search-btn">🔍 Rechercher</button>
      </div>
      <div id="u-list"><div class="spinner"></div></div>
      <div class="pagination" id="u-pagination"></div>`;

    const load = async () => {
      const list = el.querySelector("#u-list");
      try {
        const data = await API.adminUsers(this.search, this.page);
        list.innerHTML = data.items.length ? `
          <div class="table-wrap"><table>
            <thead><tr><th>Pseudo</th><th>E-mail</th><th>Rôle</th><th>Crédits</th><th>Inscrit</th><th>Dernière connexion</th><th>Statut</th><th>Actions</th></tr></thead>
            <tbody>${data.items.map((u) => `
              <tr>
                <td><b>${esc(u.username)}</b></td>
                <td class="muted">${esc(u.email)}</td>
                <td>${u.role === "ADMIN" ? "👑 ADMIN" : "USER"}</td>
                <td><b>${u.credits}</b></td>
                <td class="muted">${fmtDate(u.created_at)}</td>
                <td class="muted">${u.last_login ? fmtDate(u.last_login) : "—"}</td>
                <td>${u.is_suspended ? '<span class="status-pill status-FAILED">SUSPENDU</span>' : '<span class="status-pill status-SUCCESS">ACTIF</span>'}</td>
                <td style="white-space:nowrap">
                  <button class="btn btn-sm" data-act="view" data-id="${u.id}">👁 Fiche</button>
                  <button class="btn btn-sm" data-act="credits" data-id="${u.id}">💰</button>
                  <button class="btn btn-sm" data-act="role" data-id="${u.id}" data-role="${u.role}">${u.role === "ADMIN" ? "⬇️" : "⬆️"}</button>
                  <button class="btn btn-sm" data-act="suspend" data-id="${u.id}" data-suspended="${u.is_suspended}">${u.is_suspended ? "✅" : "🚫"}</button>
                  <button class="btn btn-sm btn-danger" data-act="delete" data-id="${u.id}">🗑</button>
                </td>
              </tr>`).join("")}</tbody>
          </table></div>` : `<div class="empty-state"><p>Aucun utilisateur trouvé.</p></div>`;

        const pages = Math.max(1, Math.ceil(data.total / data.page_size));
        el.querySelector("#u-pagination").innerHTML = pages > 1
          ? `<button class="btn btn-sm" id="u-prev" ${this.page <= 1 ? "disabled" : ""}>←</button>
             <span class="muted small">${this.page}/${pages}</span>
             <button class="btn btn-sm" id="u-next" ${this.page >= pages ? "disabled" : ""}>→</button>` : "";
        el.querySelector("#u-prev")?.addEventListener("click", () => { this.page--; load(); });
        el.querySelector("#u-next")?.addEventListener("click", () => { this.page++; load(); });

        list.querySelectorAll("button[data-act]").forEach((btn) => {
          btn.addEventListener("click", () => this.action(btn.dataset, load));
        });
      } catch (e) {
        list.innerHTML = `<div class="empty-state"><p>${esc(e.message)}</p></div>`;
      }
    };

    const doSearch = debounce(() => { this.search = el.querySelector("#u-search").value.trim(); this.page = 1; load(); });
    el.querySelector("#u-search").addEventListener("input", doSearch);
    el.querySelector("#u-search-btn").addEventListener("click", () => { this.search = el.querySelector("#u-search").value.trim(); this.page = 1; load(); });
    load();
  },

  async action(ds, reload) {
    try {
      if (ds.act === "view") {
        const d = await API.adminUser(ds.id);
        this.showDetail(d);
      } else if (ds.act === "credits") {
        this.showCreditsDialog(ds.id, reload);
      } else if (ds.act === "role") {
        const newRole = ds.role === "ADMIN" ? "USER" : "ADMIN";
        if (confirm(`Passer cet utilisateur en rôle ${newRole} ?`)) {
          await API.adminPatchUser(ds.id, { role: newRole });
          toast("Rôle modifié.", "success");
          reload();
        }
      } else if (ds.act === "suspend") {
        const suspended = ds.suspended === "true";
        if (confirm(suspended ? "Réactiver ce compte ?" : "Suspendre ce compte ?")) {
          await API.adminPatchUser(ds.id, { is_suspended: !suspended });
          toast(suspended ? "Compte réactivé." : "Compte suspendu.", "success");
          reload();
        }
      } else if (ds.act === "delete") {
        if (confirm("Supprimer définitivement ce compte et toutes ses données ?")) {
          await API.adminDeleteUser(ds.id);
          toast("Compte supprimé.", "success");
          reload();
        }
      }
    } catch (e) { toast(e.message, "error"); }
  },

  showDetail(d) {
    openModal(`
      <h3 style="margin-bottom:10px">👤 ${esc(d.user.username)}</h3>
      <p class="muted">${esc(d.user.email)} · inscrit le ${fmtDate(d.user.created_at)} · solde : <b>${d.credits.balance}</b> crédits</p>
      <h4 style="margin:14px 0 6px">Connexions récentes</h4>
      ${d.logins.length ? d.logins.map((l) => `<div class="small muted">${fmtDate(l.created_at)} — ${l.success ? "✅" : "❌"} (${esc(l.ip)})</div>`).join("") : '<p class="muted small">Aucune.</p>'}
      <h4 style="margin:14px 0 6px">Dernières générations</h4>
      ${d.generations.length ? d.generations.map((g) => `<div class="small"><span class="status-pill status-${g.status}">${g.status}</span> ${g.kind} — ${esc(g.prompt.slice(0, 80))}</div>`).join("") : '<p class="muted small">Aucune.</p>'}
      <h4 style="margin:14px 0 6px">Historique de crédits</h4>
      ${d.credit_history.length ? d.credit_history.map((r) => `<div class="small ${r.delta >= 0 ? "delta-pos" : "delta-neg"}">${r.delta >= 0 ? "+" : ""}${r.delta} — <span class="muted">${esc(r.reason)}</span></div>`).join("") : '<p class="muted small">Aucun mouvement.</p>'}
    `);
  },

  showCreditsDialog(userId, reload) {
    openModal(`
      <h3 style="margin-bottom:12px">💰 Opération de crédits</h3>
      <form id="credit-form">
        <div class="field"><label>Action</label>
          <select name="action">
            <option value="add">Ajouter des crédits</option>
            <option value="remove">Retirer des crédits</option>
            <option value="set">Définir le solde</option>
            <option value="reset">Réinitialiser (renouvellement)</option>
          </select>
        </div>
        <div class="field"><label>Montant (pour add / remove / set)</label><input type="number" name="amount" min="0" value="100"></div>
        <div class="field"><label>Raison (obligatoire, journalisée)</label><input name="reason" minlength="3" required placeholder="Ex : compensation incident"></div>
        <button class="btn btn-primary" type="submit">Valider</button>
      </form>`,
      (modal) => {
        modal.querySelector("#credit-form").addEventListener("submit", async (e) => {
          e.preventDefault();
          const f = e.target;
          try {
            const res = await API.adminCredits(userId, {
              action: f.action.value,
              amount: f.action.value === "reset" ? null : Number(f.amount.value),
              reason: f.reason.value.trim(),
            });
            toast(`Opération effectuée — nouveau solde : ${res.balance}`, "success");
            closeModal();
            reload();
          } catch (ex) { toast(ex.message, "error"); }
        });
      },
    );
  },
};

/* ---------------- Crédits (globaux) ---------------- */

AdminViews.credits = {
  async render(el) {
    el.innerHTML = adminTabs("#/admin/credits") + `
      <h2 class="section-title">💰 Gestion des crédits</h2>
      <div class="card">
        <div class="card-title">🎁 Accorder des crédits à TOUS les utilisateurs</div>
        <form id="grant-all-form">
          <div class="grid grid-2">
            <div class="field"><label>Montant par utilisateur</label><input type="number" name="amount" min="1" value="100" required></div>
            <div class="field"><label>Raison (journalisée)</label><input name="reason" minlength="3" required placeholder="Ex : événement spécial"></div>
          </div>
          <button class="btn btn-primary" type="submit">Accorder à tous</button>
        </form>
      </div>
      <div class="card" style="margin-top:16px">
        <div class="card-title">ℹ️ Rappel du fonctionnement</div>
        <p class="muted">Chaque utilisateur reçoit automatiquement ses crédits chaque heure (solde remis à zéro puis régénéré).
        Les opérations manuelles ci-dessus sont <b>journalisées</b> (solde + raison) et visibles dans l'historique de crédits de chaque utilisateur
        (onglet Utilisateurs → Fiche).</p>
      </div>`;

    el.querySelector("#grant-all-form").addEventListener("submit", async (e) => {
      e.preventDefault();
      const f = e.target;
      if (!confirm(`Accorder ${f.amount.value} crédits à TOUS les utilisateurs ?`)) return;
      try {
        const res = await API.adminGrantAll({ amount: Number(f.amount.value), reason: f.reason.value.trim() });
        toast(`${res.amount} crédits accordés à ${res.users_granted} utilisateur(s).`, "success");
      } catch (ex) { toast(ex.message, "error"); }
    });
  },
};

/* ---------------- Paramètres ---------------- */

AdminViews.settings = {
  async render(el) {
    el.innerHTML = adminTabs("#/admin/parametres") + `<div class="spinner"></div>`;
    try {
      const data = await API.adminSettings();
      const s = data.settings, p = data.providers;
      const num = (key, label, hint) => `
        <div class="settings-row">
          <div class="info"><b>${label}</b><span>${hint}</span></div>
          <input type="number" min="0" max="1000000" value="${s[key]}" data-key="${key}">
        </div>`;
      const toggle = (key, label, hint) => `
        <div class="settings-row">
          <div class="info"><b>${label}</b><span>${hint}</span></div>
          <label class="toggle"><input type="checkbox" data-key="${key}" ${s[key] ? "checked" : ""}><span class="slider"></span></label>
        </div>`;
      const provider = (name, info, label) => `
        <div class="settings-row">
          <div class="info"><b>${label}</b><span>Variables : ${info.env.join(", ")} — modèle : ${esc(info.model || "—")}</span></div>
          <span class="provider-status"><span class="dot ${info.configured ? "on" : "off"}"></span>${info.configured ? "Configuré" : "Non configuré"}</span>
        </div>`;

      el.innerHTML = adminTabs("#/admin/parametres") + `
        <h2 class="section-title">⚙️ Paramètres</h2>
        <div class="card">
          <div class="card-title">💰 Coûts & renouvellement</div>
          ${num("credits.hourly_grant", "Crédits accordés chaque heure", "Non cumulatifs : le solde est remis à cette valeur à chaque heure.")}
          ${num("cost.chat", "Coût d'une demande au chat", "En crédits.")}
          ${num("cost.image", "Coût d'une image", "En crédits.")}
          ${num("cost.video", "Coût d'une vidéo", "En crédits.")}
          ${num("cost.code", "Coût d'une génération de code", "En crédits.")}
        </div>
        <div class="card" style="margin-top:16px">
          <div class="card-title">🎛️ Fonctions IA</div>
          ${toggle("features.chat", "Chat IA", "Désactivé = les demandes sont bloquées.")}
          ${toggle("features.image", "Génération d'images", "Désactivé = les demandes sont bloquées.")}
          ${toggle("features.video", "Génération de vidéos", "Désactivé = les demandes sont bloquées.")}
          ${toggle("features.code", "Génération de code", "Désactivé = les demandes sont bloquées.")}
        </div>
        <div class="card" style="margin-top:16px">
          <div class="card-title">🚫 Limites</div>
          ${num("limits.max_prompt_length", "Longueur maximale d'un prompt", "En caractères.")}
          ${num("limits.max_concurrent_generations", "Générations simultanées", "Images / vidéos en cours par utilisateur.")}
          ${num("limits.max_generations_per_hour", "Demandes par heure", "Toutes générations confondues par utilisateur.")}
        </div>
        <div class="card" style="margin-top:16px">
          <div class="card-title">🔌 Fournisseurs IA (côté serveur)</div>
          ${provider("chat", p.chat, "Chat & code")}
          ${provider("image", p.image, "Images")}
          ${provider("video", p.video, "Vidéos")}
          <p class="muted small" style="margin-top:10px">Les clés API vivent dans le fichier <code>.env</code> du serveur et ne sont jamais envoyées au navigateur.
          Un fournisseur non configuré renvoie un message explicatif au lieu de simuler une génération.</p>
        </div>
        <div style="margin-top:16px"><button class="btn btn-primary" id="save-settings">💾 Enregistrer les paramètres</button></div>`;

      el.querySelector("#save-settings").addEventListener("click", async () => {
        const payload = {};
        el.querySelectorAll("input[type=number][data-key]").forEach((i) => { payload[i.dataset.key] = Number(i.value); });
        el.querySelectorAll("input[type=checkbox][data-key]").forEach((i) => { payload[i.dataset.key] = i.checked; });
        try {
          const res = await API.adminSaveSettings(payload);
          const errs = Object.entries(res.errors || {});
          if (errs.length) toast("Partiellement enregistré : " + errs.map(([k, v]) => `${k} : ${v}`).join(" ; "), "warning");
          else toast("Paramètres enregistrés.", "success");
        } catch (ex) { toast(ex.message, "error"); }
      });
    } catch (e) {
      el.innerHTML = adminTabs("#/admin/parametres") + `<div class="empty-state"><p>${esc(e.message)}</p></div>`;
    }
  },
};

/* ---------------- Journaux ---------------- */

AdminViews.logs = {
  async render(el) {
    el.innerHTML = adminTabs("#/admin/journaux") + `
      <h2 class="section-title">📜 Journaux d'administration</h2>
      <div class="card"><div class="card-title">Actions administrateur</div><div id="log-admin"><div class="spinner"></div></div></div>
      <div class="card" style="margin-top:16px"><div class="card-title">Erreurs techniques</div><div id="log-errors"><div class="spinner"></div></div></div>`;
    try {
      const d = await API.adminLogs();
      el.querySelector("#log-admin").innerHTML = d.admin.length
        ? d.admin.map((r) => `<div class="small" style="padding:6px 0;border-bottom:1px solid var(--border)">
            <b>${esc(r.action)}</b> <span class="muted">— ${fmtDate(r.created_at)}</span>
            ${r.details ? `<div class="muted small">${esc(JSON.stringify(r.details))}</div>` : ""}
          </div>`).join("")
        : `<p class="muted">Aucune action.</p>`;
      el.querySelector("#log-errors").innerHTML = d.errors.length
        ? d.errors.map((r) => `<div class="small" style="padding:6px 0;border-bottom:1px solid var(--border);color:var(--danger)">
            ${esc(r.message)} <span class="muted">— ${fmtDate(r.created_at)}</span>
            ${r.context ? `<div class="muted small">${esc(JSON.stringify(r.context))}</div>` : ""}
          </div>`).join("")
        : `<p class="muted">Aucune erreur enregistrée. 🎉</p>`;
    } catch (e) {
      el.innerHTML = adminTabs("#/admin/journaux") + `<div class="empty-state"><p>${esc(e.message)}</p></div>`;
    }
  },
};

/* ---------- Modale ---------- */

function openModal(html, after) {
  closeModal();
  const lb = document.createElement("div");
  lb.className = "lightbox";
  lb.id = "kyro-modal";
  lb.innerHTML = `<div class="card" style="max-width:640px;width:100%;max-height:80vh;overflow-y:auto"><span class="close" style="position:absolute;top:18px;right:22px;font-size:2rem;cursor:pointer;color:#fff">×</span>${html}</div>`;
  lb.addEventListener("click", (e) => { if (e.target === lb || e.target.classList.contains("close")) closeModal(); });
  document.body.appendChild(lb);
  if (after) after(lb);
}

function closeModal() { document.getElementById("kyro-modal")?.remove(); }
