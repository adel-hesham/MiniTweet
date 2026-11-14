const SERVICES = [
  { name: "user-service", tech: "Python", state: "built" },
  { name: "tweet-service", tech: "Node.js", state: "built" },
  { name: "like-service", tech: "Node.js", state: "built" },
  { name: "notification-service", tech: "Node.js", state: "built" },
  { name: "monitor-service", tech: "Python", state: "step 5" },
];

export default function SystemPanel() {
  return (
    <div className="rounded-2xl border border-black/5 bg-card p-6 shadow-sm dark:border-white/10 dark:bg-card-dark">
      <h2 className="text-2xl font-extrabold tracking-tight">Live system view</h2>
      <p className="mt-1 text-sm opacity-70">
        The live dashboard (service status, API requests and RabbitMQ messages) arrives in step 5.
        For now this shows the plan.
      </p>

      <ul className="mt-5 space-y-2">
        {SERVICES.map((service) => (
          <li
            key={service.name}
            className="flex items-center justify-between rounded-xl border border-black/5 px-4 py-3 dark:border-white/10"
          >
            <div>
              <p className="text-sm font-semibold">{service.name}</p>
              <p className="text-xs opacity-60">{service.tech}</p>
            </div>
            <span
              className={`rounded-full px-3 py-1 text-xs font-semibold ${
                service.state === "built"
                  ? "bg-emerald-100 text-emerald-700 dark:bg-emerald-900/40 dark:text-emerald-300"
                  : "bg-gray-200 text-gray-600 dark:bg-gray-700 dark:text-gray-300"
              }`}
            >
              {service.state}
            </span>
          </li>
        ))}
      </ul>
    </div>
  );
}
