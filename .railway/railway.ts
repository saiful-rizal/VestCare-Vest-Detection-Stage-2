import { defineRailway, project, service } from "railway/iac";
// This repository manages only its own resources in the environment. Other
// repositories export their own partial name.
// See https://docs.railway.com/infrastructure-as-code#multi-repo-projects
export const partial = "vestcare-detection-object";
export default defineRailway(() => {
  const vestcareDetectionObject = service("vestcare-detection-object", {
    build: { buildEnvironment: "V3", builder: "DOCKERFILE" },
    healthcheck: "/readyz",
    healthcheckTimeout: 300,
    replicas: { "iad": 1 },
  });

  return project("vestcare-detection-object", {
    variables: { managed: false },
    resources: [vestcareDetectionObject],
  });
});
