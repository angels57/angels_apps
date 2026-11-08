import { registry } from "@web/core/registry";

import { RunOnWebLoader } from "./loader";

// What other addons use:
//   const runonweb = useService("angels_runonweb");
//   const { text } = await runonweb.run("emoji", "I love pizza");
// The configuration is asked for the first time a task is used, not on every page load.
export const runonwebService = {
    dependencies: ["orm"],
    start(env, { orm }) {
        const loader = new RunOnWebLoader();
        let configPromise = null;

        function getConfig(refresh = false) {
            if (refresh || !configPromise) {
                configPromise = orm.call("angels.runonweb", "get_config", []);
                configPromise.catch(() => (configPromise = null));
            }
            return configPromise;
        }

        return {
            getConfig,
            async load(task, options) {
                return loader.load(task, await getConfig(), options);
            },
            async run(task, input, options) {
                return loader.run(task, await getConfig(), input, options);
            },
            onProgress: (listener) => loader.onProgress(listener),
            dispose: () => loader.dispose(),
        };
    },
};

registry.category("services").add("angels_runonweb", runonwebService);
