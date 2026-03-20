import "@/App.css";
import { BrowserRouter, Routes, Route } from "react-router-dom";
import { AppShell } from "./components/AppShell";
import Overview from "./pages/Overview";
import Arbitrage from "./pages/Arbitrage";
import Sniper from "./pages/Sniper";
import Weather from "./pages/Weather";
import Positions from "./pages/Positions";
import Analytics from "./pages/Analytics";
import GlobalAnalytics from "./pages/GlobalAnalytics";
import Risk from "./pages/Risk";
import Markets from "./pages/Markets";
import Settings from "./pages/Settings";
import QuantLab from "./pages/QuantLab";

function App() {
  return (
    <div className="App">
      <BrowserRouter>
        <Routes>
          <Route element={<AppShell />}>
            <Route path="/" element={<Overview />} />
            <Route path="/arbitrage" element={<Arbitrage />} />
            <Route path="/sniper" element={<Sniper />} />
            <Route path="/weather" element={<Weather />} />
            <Route path="/quant-lab" element={<QuantLab />} />
            <Route path="/positions" element={<Positions />} />
            <Route path="/analytics" element={<Analytics />} />
            <Route path="/global-analytics" element={<GlobalAnalytics />} />
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
