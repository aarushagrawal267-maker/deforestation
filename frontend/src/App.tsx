import { Route, Routes } from "react-router-dom";
import { Shell } from "./components/layout/Shell";
import ChangePage from "./pages/Change";
import DatasetsPage from "./pages/Datasets";
import DocsPage from "./pages/Docs";
import EvaluationPage from "./pages/Evaluation";
import ExplorerPage from "./pages/Explorer";
import HistoryPage from "./pages/History";
import InvestigatePage from "./pages/Investigate";
import LabPage from "./pages/Lab";
import MapPage from "./pages/MapPage";
import OverviewPage from "./pages/Overview";
import SegmentationPage from "./pages/Segmentation";

export default function App() {
  return (
    <Shell>
      <Routes>
        <Route path="/" element={<OverviewPage />} />
        <Route path="/map" element={<MapPage />} />
        <Route path="/explorer" element={<ExplorerPage />} />
        <Route path="/segmentation" element={<SegmentationPage />} />
        <Route path="/change" element={<ChangePage />} />
        <Route path="/investigate" element={<InvestigatePage />} />
        <Route path="/investigate/:id" element={<InvestigatePage />} />
        <Route path="/datasets" element={<DatasetsPage />} />
        <Route path="/lab" element={<LabPage />} />
        <Route path="/evaluation" element={<EvaluationPage />} />
        <Route path="/history" element={<HistoryPage />} />
        <Route path="/docs" element={<DocsPage />} />
        <Route path="/docs/:doc" element={<DocsPage />} />
        <Route path="*" element={<div className="text-muted">Page not found.</div>} />
      </Routes>
    </Shell>
  );
}
