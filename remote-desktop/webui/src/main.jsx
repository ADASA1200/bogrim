import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import "./theme.css";
import { applyStoredTheme } from "./theme.js";
import App from "./App.jsx";

applyStoredTheme(); // לפני ה-render הראשון - בלי זה יש הבהוב של הערכה הכהה

createRoot(document.getElementById("root")).render(
  <StrictMode>
    <App />
  </StrictMode>
);
