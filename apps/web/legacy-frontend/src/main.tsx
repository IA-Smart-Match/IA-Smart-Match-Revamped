import React from "react";
import ReactDOM from "react-dom/client";

import App from "./app/App";
import "./styles/index.css";

const adobeFontsUrl = import.meta.env.VITE_ADOBE_FONTS_URL;

if (adobeFontsUrl) {
  const adobeFontsLink = document.createElement("link");
  adobeFontsLink.rel = "stylesheet";
  adobeFontsLink.href = adobeFontsUrl;
  adobeFontsLink.dataset.fontProvider = "adobe";
  document.head.appendChild(adobeFontsLink);
}

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
);
