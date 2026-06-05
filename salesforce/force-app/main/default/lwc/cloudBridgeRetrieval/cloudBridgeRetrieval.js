import { LightningElement, track } from 'lwc';
import { ShowToastEvent } from 'lightning/platformShowToastEvent';
import defaultOrgIdLabel from '@salesforce/label/c.CloudBridge_Default_Org_Id';
import createRetrievalJob from '@salesforce/apex/CloudBridgeRetrievalController.createRetrievalJob';
import getRetrievalJob from '@salesforce/apex/CloudBridgeRetrievalController.getRetrievalJob';
import listRecentRetrievalJobs from '@salesforce/apex/CloudBridgeRetrievalController.listRecentRetrievalJobs';

const POLL_INTERVAL_MS = 4000;

export default class CloudBridgeRetrieval extends LightningElement {
    @track rows = [];
    @track packageXml = '';
    @track orgId = defaultOrgIdLabel || '';
    @track deploymentRequester = '';
    @track statusMessage = '';
    @track currentJob = {};
    @track recentJobs = [];

    draftType = '';
    draftMembers = '';
    apiVersion = '62.0';
    rowCounter = 1;
    pollingHandle;
    isBusy = false;

    connectedCallback() {
        this.generatePackageXml();
        this.loadRecentJobs();
    }

    disconnectedCallback() {
        this.stopPolling();
    }

    get isSuccess() {
        return this.currentJob && this.currentJob.status === 'success';
    }

    handleDraftTypeChange(event) {
        this.draftType = (event.target.value || '').trim();
    }

    handleDraftMembersChange(event) {
        this.draftMembers = event.target.value || '';
    }

    handleApiVersionChange(event) {
        this.apiVersion = event.target.value || '62.0';
    }

    handlePackageXmlChange(event) {
        this.packageXml = event.target.value || '';
    }

    handleOrgIdChange(event) {
        this.orgId = (event.target.value || '').trim();
    }

    handleDeploymentRequesterChange(event) {
        this.deploymentRequester = (event.target.value || '').trim();
    }

    addMetadataRow() {
        if (!this.draftType) {
            this.showToast('Metadata type required', 'Enter a metadata type first.', 'warning');
            return;
        }

        const members = this.draftMembers
            .split(',')
            .map((value) => value.trim())
            .filter((value) => !!value);

        if (members.length === 0) {
            members.push('*');
        }

        const row = {
            id: String(this.rowCounter++),
            type: this.draftType,
            members,
            memberPreview: members.join(', ')
        };

        this.rows = [...this.rows, row];
        this.draftType = '';
        this.draftMembers = '';
        this.generatePackageXml();
    }

    removeMetadataRow(event) {
        const index = Number(event.currentTarget.dataset.index);
        if (Number.isNaN(index)) {
            return;
        }

        this.rows = this.rows.filter((_, idx) => idx !== index);
        this.generatePackageXml();
    }

    clearAll() {
        this.rows = [];
        this.packageXml = '';
        this.deploymentRequester = '';
        this.statusMessage = '';
        this.currentJob = {};
        this.stopPolling();
    }

    generatePackageXml() {
        if (!this.rows.length) {
            this.packageXml =
                '<?xml version="1.0" encoding="UTF-8"?>\n' +
                '<Package xmlns="http://soap.sforce.com/2006/04/metadata">\n' +
                '    <version>' + this.apiVersion + '</version>\n' +
                '</Package>';
            return;
        }

        const typesXml = this.rows
            .map((row) => {
                const memberXml = row.members
                    .map((member) => `        <members>${this.escapeXml(member)}</members>`)
                    .join('\n');
                return [
                    '    <types>',
                    memberXml,
                    `        <name>${this.escapeXml(row.type)}</name>`,
                    '    </types>'
                ].join('\n');
            })
            .join('\n');

        this.packageXml = [
            '<?xml version="1.0" encoding="UTF-8"?>',
            '<Package xmlns="http://soap.sforce.com/2006/04/metadata">',
            typesXml,
            `    <version>${this.escapeXml(this.apiVersion)}</version>`,
            '</Package>'
        ].join('\n');
    }

    async triggerRetrieval() {
        if (!this.packageXml) {
            this.showToast('package.xml missing', 'Generate or paste package.xml first.', 'error');
            return;
        }

        this.isBusy = true;
        this.statusMessage = 'Creating retrieval job...';

        try {
            const result = await createRetrievalJob({
                packageXml: this.packageXml,
                orgId: this.orgId,
                useBackground: true,
                deploymentRequester: this.deploymentRequester
            });

            this.currentJob = result || {};
            this.statusMessage = 'Retrieval queued. Polling job status...';
            this.showToast('Retrieval queued', `Job ${this.currentJob.id}`, 'success');
            this.startPolling();
            await this.loadRecentJobs();
        } catch (error) {
            this.statusMessage = 'Failed to create retrieval job.';
            this.showToast('Create retrieval failed', this.parseError(error), 'error');
        } finally {
            this.isBusy = false;
        }
    }

    startPolling() {
        this.stopPolling();

        this.pollingHandle = window.setInterval(async () => {
            if (!this.currentJob || !this.currentJob.id) {
                this.stopPolling();
                return;
            }

            try {
                const updated = await getRetrievalJob({ jobId: this.currentJob.id });
                this.currentJob = updated || this.currentJob;
                this.statusMessage = `Job status: ${this.currentJob.status}`;

                if (this.currentJob.status === 'success') {
                    this.statusMessage = 'Retrieval completed. Download is ready.';
                    this.showToast('Retrieval complete', `Job ${this.currentJob.id}`, 'success');
                    this.stopPolling();
                    await this.loadRecentJobs();
                } else if (this.currentJob.status === 'failed') {
                    this.statusMessage = 'Retrieval failed.';
                    this.showToast('Retrieval failed', this.currentJob.error_message || 'Check backend logs.', 'error');
                    this.stopPolling();
                    await this.loadRecentJobs();
                }
            } catch (error) {
                this.statusMessage = 'Polling stopped due to API error.';
                this.showToast('Polling error', this.parseError(error), 'error');
                this.stopPolling();
            }
        }, POLL_INTERVAL_MS);
    }

    stopPolling() {
        if (this.pollingHandle) {
            window.clearInterval(this.pollingHandle);
            this.pollingHandle = null;
        }
    }

    async loadRecentJobs() {
        try {
            const jobs = await listRecentRetrievalJobs({ limitSize: 10 });
            this.recentJobs = (jobs || []).map((job) => ({
                ...job,
                shortId: job.id ? String(job.id).substring(0, 8) : 'unknown'
            }));
        } catch (error) {
            this.showToast('Recent jobs load failed', this.parseError(error), 'warning');
        }
    }

    downloadSfdx() {
        this.openDownload('sfdx');
    }

    downloadJson() {
        this.openDownload('json');
    }

    openDownload(format) {
        if (!this.currentJob || !this.currentJob.id) {
            this.showToast('No job selected', 'Create and complete a retrieval first.', 'warning');
            return;
        }

        const key = format === 'sfdx' ? 'download_sfdx_url' : 'download_json_url';
        const url = this.currentJob[key];

        if (!url) {
            this.showToast('Download link unavailable', 'Poll job status again and retry.', 'warning');
            return;
        }

        window.open(url, '_blank');
    }

    escapeXml(rawValue) {
        return String(rawValue)
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;')
            .replace(/'/g, '&apos;');
    }

    parseError(error) {
        if (!error) {
            return 'Unknown error';
        }

        if (error.body && error.body.message) {
            return error.body.message;
        }

        if (error.message) {
            return error.message;
        }

        try {
            return JSON.stringify(error);
        } catch (stringifyError) {
            return 'Unknown error';
        }
    }

    showToast(title, message, variant) {
        this.dispatchEvent(
            new ShowToastEvent({
                title,
                message,
                variant
            })
        );
    }
}
