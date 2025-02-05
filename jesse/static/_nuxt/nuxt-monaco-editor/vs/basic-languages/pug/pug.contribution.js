/*!-----------------------------------------------------------------------------
 * Copyright (c) Microsoft Corporation. All rights reserved.
 * Version: 0.50.0(c321d0fbecb50ab8a5365fa1965476b0ae63fc87)
 * Released under the MIT license
 * https://github.com/microsoft/monaco-editor/blob/main/LICENSE.txt
 *-----------------------------------------------------------------------------*/


// src/basic-languages/pug/pug.contribution.ts
import { registerLanguage } from "../_.contribution.js";
registerLanguage({
  id: "pug",
  extensions: [".jade", ".pug"],
  aliases: ["Pug", "Jade", "jade"],
  loader: () => {
    if (false) {
      return new Promise((resolve, reject) => {
        __require(["vs/basic-languages/pug/pug"], resolve, reject);
      });
    } else {
      return import("./pug.js");
    }
  }
});
