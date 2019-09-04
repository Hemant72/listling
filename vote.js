// Prototype for list of voters with contextual

       this._data = ...
            greets: new micro.Collection("/api/greetings"),
            greetsComplete: false,
            onVotesActivate: () => {
                if (this._data.greets.items.length === 0) {
                    this.querySelector(".hello-greets button").trigger();
                }
            },
        ...
        this._data.greets.events.addEventListener("fetch", () => {
            this._data.greetsComplete = this._data.greets.complete;
        });

            <div class="micro-panel">
                <button class="action">Vote</button>
                <div>
                    <p tabindex="0">42</p>
                    <micro-contextual data-onactivate="onVotesActivate" style="right: auto;">
                        <div class="hello-greets micro-entity-list" data-class-hello-greets-complete="greetsComplete">
                            <ul data-content="list greets.items 'greeting'">
                                <template>
                                    <li class="micro-panel"><p data-content="greeting.text"></p></li>
                                </template>
                            </ul>
                            <footer class="micro-panel">
                                <button is="micro-button" class="link micro-panel-main" data-run="bind fetchCollection greets 3" style="white-space: nowrap">
                                    <i class="fa fa-fw fa-ellipsis-v"></i> More
                                </button>
                            </footer>
                        </div>
                    </micro-contextual>
                </div>
            </div>

            .micro-entity-list > footer {
                border-top: 1px solid var(--micro-color-delimiter);
            }

            .hello-greets-complete > footer {
                display: none;
            }
