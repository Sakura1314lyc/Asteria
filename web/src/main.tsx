import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import "@primer/primitives/dist/css/functional/themes/light.css";
import "@primer/primitives/dist/css/functional/themes/dark-dimmed.css";
import { App } from "./App";
import "./styles/global.css";

document.documentElement.dataset.colorMode = "light";
document.documentElement.dataset.lightTheme = "light";

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <App />
  </StrictMode>
);
