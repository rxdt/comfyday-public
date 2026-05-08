const initialScene = window.__INITIAL_SCENE__;
const maxForecastHours = window.__MAX_FORECAST_HOURS__ || 12;
const defaultLocationQuery = "94110";

const elements = {
  basePhoto: document.getElementById("base-photo"),
  missingBase: document.getElementById("missing-base"),
  sceneLayers: document.getElementById("scene-layers"),
  temperature: document.getElementById("temperature"),
  rainChance: document.getElementById("rain-chance"),
  weatherKind: document.getElementById("weather-kind"),
  description: document.getElementById("description"),
  weatherTitlePrefix: document.getElementById("weather-title-prefix"),
  windFragment: document.getElementById("wind-fragment"),
  outfitNote: document.getElementById("outfit-note"),
  statusLine: document.getElementById("status-line"),
  lastUpdated: document.getElementById("last-updated"),
  locationLabel: document.getElementById("location-label"),
  timeForm: document.getElementById("time-form"),
  hoursAhead: document.getElementById("hours-ahead"),
  locationQuery: document.getElementById("location-query"),
};

let currentScene = null;

function applyLayerFit(img, fit) {
  const style = img.style;
  const setStyle = (property, value, fallback) => {
    style[property] = value !== undefined && value !== null ? String(value) : fallback;
  };

  style.left = "0";
  style.top = "0";
  style.width = "100%";
  style.height = "100%";
  style.opacity = "1";
  style.zIndex = "1";
  style.clipPath = "none";
  style.objectFit = "cover";
  style.objectPosition = "center top";
  style.transformOrigin = "center top";
  style.removeProperty("transform");
  style.inset = "0";

  if (!fit || typeof fit !== "object") {
    return;
  }

  const hasExactBox =
    fit.left !== undefined ||
    fit.top !== undefined ||
    fit.width !== undefined ||
    fit.height !== undefined;

  if (hasExactBox) {
    // Inline `inset: auto` disables stylesheet `inset: 0` defaults so explicit box
    // coordinates can control absolute-positioned registered layers predictably.
    style.inset = "auto";
    style.width = "auto";
    style.height = "auto";
  }

  setStyle("left", fit.left, style.left);
  setStyle("top", fit.top, style.top);
  setStyle("width", fit.width, style.width);
  setStyle("height", fit.height, style.height);
  setStyle("clipPath", fit.clipPath, style.clipPath);
  setStyle("opacity", fit.opacity, style.opacity);
  setStyle("zIndex", fit.zIndex, style.zIndex);
  setStyle("objectFit", fit.objectFit, style.objectFit);
  setStyle("objectPosition", fit.objectPosition, style.objectPosition);
  setStyle("transformOrigin", fit.transformOrigin, style.transformOrigin);
  if (fit.transform !== undefined && fit.transform !== null) {
    style.transform = String(fit.transform);
  }
}

function setBaseImage(scene) {
  const { basePhoto, missingBase } = elements;
  const cacheKey = encodeURIComponent(`${scene.generated_image_url || scene.base_image_url}:${scene.last_updated}`);
  basePhoto.src = `${scene.base_image_url}?v=${cacheKey}`;
  basePhoto.onload = () => {
    basePhoto.classList.remove("is-hidden");
    missingBase.classList.add("is-hidden");
  };
  basePhoto.onerror = () => {
    basePhoto.classList.add("is-hidden");
    missingBase.classList.remove("is-hidden");
  };
}

function renderLayers(scene) {
  elements.sceneLayers.innerHTML = "";

  if (!scene.layers.length) {
    return;
  }

  scene.layers.forEach((layer) => {
    const layerImage = document.createElement("img");
    layerImage.className = "scene-layer-image";
    layerImage.alt = layer.label;
    layerImage.src = `${layer.url}?v=${scene.version}`;
    applyLayerFit(layerImage, layer.fit);
    layerImage.onerror = () => {
      layerImage.classList.add("is-hidden");
    };
    elements.sceneLayers.appendChild(layerImage);
  });
}

function renderScene(scene) {
  currentScene = scene;
  if (elements.locationLabel) {
    elements.locationLabel.textContent = scene.location_name || "San Francisco";
  }
  if (elements.weatherTitlePrefix) {
    elements.weatherTitlePrefix.textContent =
      scene.hours_ahead === 0
        ? "Current weather in"
        : `Forecast weather in ${scene.hours_ahead} hour${scene.hours_ahead === 1 ? "" : "s"} for`;
  }
  const temperature = Number(scene.temperature_f).toFixed(0);
  const feelsLike =
    scene.feels_like_f === undefined || scene.feels_like_f === null
      ? ""
      : ` (feels like ${Number(scene.feels_like_f).toFixed(0)})`;
  elements.temperature.textContent = `${temperature}${feelsLike}`;
  elements.rainChance.textContent = String(scene.precip_probability_pct);
  elements.weatherKind.textContent = scene.rain_level === "none" ? (scene.night ? "night" : "sun") : "rain";
  elements.description.textContent =
    scene.hours_ahead === 0
      ? `${scene.description.toLowerCase()} right now`
      : `${scene.description.toLowerCase()} ${scene.hours_ahead} hour${scene.hours_ahead === 1 ? "" : "s"} from now`;
  elements.windFragment.textContent = scene.wind_label ? ` · ${scene.wind_label}` : "";
  elements.outfitNote.textContent = scene.outfit_note || "";
  elements.lastUpdated.textContent = new Date(scene.last_updated).toLocaleString();
  elements.statusLine.textContent = "";

  elements.hoursAhead.value = String(scene.hours_ahead);
  if (elements.locationQuery) {
    elements.locationQuery.value = elements.locationQuery.value.trim() || scene.query || defaultLocationQuery;
  }

  setBaseImage(scene);
  renderLayers(scene);
}

async function loadScene(hoursAhead, query) {
  const controller = new AbortController();
  const timeoutId = window.setTimeout(() => controller.abort(), 12000);
  try {
    const params = new URLSearchParams({
      hours_ahead: String(hoursAhead),
    });
    if (query && query.trim()) {
      params.set("query", query.trim());
    }
    const response = await fetch(`/api/scene?${params.toString()}`, {
      cache: "no-store",
      signal: controller.signal,
    });
    if (!response.ok) {
      throw new Error(`Request failed with ${response.status}`);
    }
    const scene = await response.json();
    renderScene(scene);
  } catch (error) {
    const message = error.name === "AbortError" ? "Request timed out." : error.message;
    elements.statusLine.textContent = `Browser refresh failed: ${message}`;
  } finally {
    window.clearTimeout(timeoutId);
  }
}

elements.timeForm.addEventListener("submit", (event) => {
  event.preventDefault();
  const requested = Number(elements.hoursAhead.value || 0);
  const normalized = Math.max(0, Math.min(maxForecastHours, Math.floor(requested)));
  elements.hoursAhead.value = String(normalized);
  loadScene(normalized, elements.locationQuery?.value || defaultLocationQuery);
});

loadScene(initialScene.hours_ahead || 0, initialScene.query || defaultLocationQuery);
