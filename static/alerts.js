/* NOAA/NWS notices are separate from station readings and the forecast beacon. */
(function (root, factory) {
  const value = factory();
  if (typeof module === "object" && module.exports) module.exports = value;
  else root.WeatherAlerts = value;
})(typeof globalThis !== "undefined" ? globalThis : this, function () {
  "use strict";
  const number = (value) => typeof value === "number" && Number.isFinite(value);
  const kind = (event) =>
    ["warning", "watch", "advisory"].find((word) =>
      String(event).toLowerCase().split(/\s+/).includes(word),
    ) || "statement";
  function pointKey(point) {
    return number(point?.latitude) && number(point?.longitude)
      ? `${point.latitude.toFixed(4)},${point.longitude.toFixed(4)}`
      : "";
  }
  function officialUrl(point) {
    return pointKey(point)
      ? `https://forecast.weather.gov/MapClick.php?lat=${point.latitude.toFixed(4)}&lon=${point.longitude.toFixed(4)}`
      : "https://www.weather.gov/";
  }
  function view(data, now = Date.now() / 1000) {
    if (!data)
      return {
        status: "loading",
        tone: "neutral",
        title: "Checking local alerts…",
        alerts: [],
        stale: false,
      };
    const stale =
      !!data.error ||
      !!data.stale ||
      !number(data.checkedAt) ||
      now - data.checkedAt > 180 ||
      data.checkedAt > now + 60;
    const alerts = (data.alerts || []).filter(
      (a) => number(a.validUntil) && a.validUntil > now,
    );
    if (alerts.length) {
      return {
        status: stale ? "stale" : "active",
        tone: kind(alerts[0].event),
        stale,
        alerts,
        title: `${stale ? "Last known: " : ""}${alerts[0].event}${alerts.length > 1 ? ` + ${alerts.length - 1} more` : ""}`,
      };
    }
    return {
      status: stale ? "unavailable" : "quiet",
      tone: stale ? "neutral" : "quiet",
      stale,
      alerts,
      title: stale ? "NWS alerts unavailable" : "No active NWS alerts",
    };
  }
  function create({ fetchAlerts, getSettings, formatDate }) {
    const $ = (id) => document.getElementById(id);
    let data = null,
      requestedPoint = "",
      pending = null,
      revision = 0,
      started = false;
    let lastAnnouncement = "",
      dialogSignature = "";
    const label = () => getSettings()?.location || "Your configured location";
    const set = (id, value) => {
      if ($(id).textContent !== value) $(id).textContent = value;
    };
    const stamp = (value) =>
      number(value) ? formatDate(value * 1000) : "Not yet checked";
    function renderDialog(model) {
      const signature = JSON.stringify([
        data,
        model.status,
        model.alerts.map((a) => a.id),
        label(),
      ]);
      if (signature === dialogSignature) return;
      dialogSignature = signature;
      const target = $("alertsList");
      target.replaceChildren();
      set(
        "alertsDialogNote",
        `${label()} · ${number(data?.checkedAt) ? `Last successful check ${stamp(data.checkedAt)}` : "Waiting for a successful NWS check"}. Checks every minute while the dashboard is open.`,
      );
      const source = $("alertsOfficialLink");
      source.href = officialUrl(getSettings());
      if (model.stale) {
        const note = document.createElement("p");
        note.className = "alerts-stale-note";
        note.textContent =
          "The feed is unavailable or overdue. Any notices below are unexpired last-known alerts; there may be newer notices. Check weather.gov for the latest information.";
        target.append(note);
      }
      if (!model.alerts.length) {
        const note = document.createElement("p");
        note.textContent =
          model.status === "quiet"
            ? "NWS returned no active alerts for these coordinates at the last successful check."
            : model.status === "loading"
              ? "Contacting the National Weather Service…"
              : "Current alert status could not be confirmed.";
        target.append(note);
      }
      for (const alert of model.alerts) {
        const card = document.createElement("article");
        card.className = "alert-detail";
        card.dataset.tone = kind(alert.event);
        const heading = document.createElement("h3");
        heading.textContent = alert.event;
        card.append(heading);
        function paragraph(value, className = "") {
          if (!value) return;
          const p = document.createElement("p");
          p.className = className;
          p.textContent = value;
          card.append(p);
        }
        paragraph(alert.headline, "alert-headline");
        paragraph(
          [
            alert.sender,
            `Severity: ${alert.severity}`,
            `Urgency: ${alert.urgency}`,
            `Certainty: ${alert.certainty}`,
          ]
            .filter(Boolean)
            .join(" · "),
          "alert-meta",
        );
        paragraph(
          `Issued: ${stamp(alert.sentAt)}${number(alert.onsetAt) ? `\nStarts: ${stamp(alert.onsetAt)}` : ""}${number(alert.endsAt) ? `\nEnds: ${stamp(alert.endsAt)}` : ""}\nNotice expires: ${stamp(alert.expiresAt)}`,
          "alert-meta",
        );
        paragraph(
          alert.area ? `NWS affected area: ${alert.area}` : "",
          "alert-area",
        );
        paragraph(alert.description, "alert-description");
        if (alert.instruction) {
          const instructions = document.createElement("h4");
          instructions.textContent = "What to do";
          card.append(instructions);
          paragraph(alert.instruction, "alert-instructions");
        }
        target.append(card);
      }
    }
    function render() {
      const model = view(data);
      const panel = $("weatherAlerts");
      panel.dataset.status = model.status;
      panel.dataset.tone = model.tone;
      set("alertsArea", `NOAA / NWS · ${label()}`);
      set("alertsTitle", model.title);
      $("alertsTitle").title = model.title;
      const first = model.alerts[0];
      let summary;
      if (first)
        summary = `${number(first.onsetAt) && first.onsetAt > Date.now() / 1000 ? `Starts ${stamp(first.onsetAt)} · ` : ""}${number(first.endsAt) ? "Ends" : "Notice expires"} ${stamp(first.endsAt ?? first.expiresAt)}${model.stale ? " · UPDATE UNAVAILABLE" : ""}`;
      else
        summary = model.stale
          ? "Current status unconfirmed · retrying automatically"
          : model.status === "loading"
            ? "Warnings, watches and advisories for your saved location"
            : "Warnings, watches and advisories · checks every minute";
      set("alertsSummary", summary);
      set(
        "alertsChecked",
        number(data?.checkedAt)
          ? `${model.stale ? "Last success" : "Checked"} ${stamp(data.checkedAt)}`
          : "Auto · every minute",
      );
      set(
        "alertsDetailsBtn",
        model.alerts.length
          ? `View ${model.alerts.length === 1 ? "alert" : `${model.alerts.length} alerts`}`
          : "Details",
      );
      const announcement = `${model.status}:${model.alerts.map((a) => `${a.id}:${a.expiresAt}`).join(",")}`;
      if (announcement !== lastAnnouncement) {
        set("alertsLive", model.title);
        lastAnnouncement = announcement;
      }
      if ($("alertsDialog").open) renderDialog(model);
    }
    function refresh() {
      const key = pointKey(getSettings());
      if (!key) return Promise.resolve();
      if (key !== requestedPoint) {
        requestedPoint = key;
        revision++;
        data = null;
        pending = null;
        render();
      }
      if (pending) return pending;
      const currentRevision = revision;
      const request = (async () => {
        try {
          const result = await fetchAlerts();
          if (currentRevision !== revision || pointKey(getSettings()) !== key)
            return;
          if (
            !result ||
            !Array.isArray(result.alerts) ||
            pointKey(result.point) !== key
          )
            throw new Error("Unreadable alert feed");
          data = result;
        } catch (_) {
          if (currentRevision !== revision || pointKey(getSettings()) !== key)
            return;
          data = {
            ...(data || {}),
            alerts: data?.alerts || [],
            stale: true,
            error: "NWS alerts could not refresh.",
          };
        } finally {
          if (currentRevision === revision) render();
        }
      })();
      pending = request;
      request.finally(() => {
        if (pending === request) pending = null;
      });
      return request;
    }
    function start() {
      if (started) return;
      started = true;
      $("alertsDetailsBtn").addEventListener("click", () => {
        renderDialog(view(data));
        $("alertsDialog").showModal();
      });
      render();
      refresh();
      setInterval(refresh, 60000);
      // Expired notices and old "no alerts" results disappear even if a request stalls.
      setInterval(render, 15000);
    }
    return { start, refresh };
  }
  return { kind, pointKey, officialUrl, view, create };
});
