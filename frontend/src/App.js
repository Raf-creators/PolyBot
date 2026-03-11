import "@/App.css";
import { BrowserRouter, Routes, Route } from "react-router-dom";
import { AppShell } from "./components/AppShell";
import Overview from "./pages/Overview";
import Arbitrage from "./pages/Arbitrage";
import Positions from "./pages/Positions";
import Risk from "./pages/Risk";
import Markets from "./pages/Markets";
import Settings from "./pages/Settings";

function App() {
  return (
    <div className="App">
      <BrowserRouter>
        <Routes>
          <Route element={<AppShell />}>
            <Route path="/" element={<Overview />} />
            <Route path="/arbitrage" element={<Arbitrage />} />
            <Route path="/positions" element={<Positions />} />
            <Route path="/risk" element={<Risk />} />
            <Route path="/markets" element={<Markets />} />
            <Route path="/settings" element={<Settings />} />
          </Route>
        </Routes>
      </BrowserRouter>
    </div>
  );
}

export default App;
