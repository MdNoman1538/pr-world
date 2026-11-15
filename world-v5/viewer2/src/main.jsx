import React from "react";
import { createRoot } from "react-dom/client";
import "@xyflow/react/dist/style.css";
import "./styles.css";
import App from "./App.jsx";
import { bootPlatform } from "./Platform.jsx";
import { getJSON } from "./model.js";
// read the person's view settings (server or this browser) before the first screen
getJSON("index.json").catch(() => {}); getJSON("meaning.json").catch(() => {});   // start the data while the settings load
Promise.race([bootPlatform(), new Promise((ok) => setTimeout(ok, 3000))]).catch(() => {}).finally(() => createRoot(document.getElementById("root")).render(<App />));
