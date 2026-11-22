
import { Outlet } from "react-router-dom";
import Header from "../common/Header";
import Sidebar from "../common/Sidebar";

function AppLayout() {
  return (
    <div className="min-h-screen bg-slate-50">

      <Header />

      <div className="flex">
        <Sidebar />

        <main className="min-w-0 flex-1 p-6">
          <Outlet />
        </main>
      </div>

    </div>
  );
}

export default AppLayout;
